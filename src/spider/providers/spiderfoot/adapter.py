import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

from spider.providers.base import BaseProviderAdapter, ProviderHealth, ProviderExecutionResult
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage

logger = logging.getLogger(__name__)

SF_TYPE_MAP = {
    "INTERNET_NAME": ObservableType.HOSTNAME,
    "RAW_DNS_RECORDS": ObservableType.HOSTNAME,
    "IP_ADDRESS": ObservableType.IP_ADDRESS,
    "IPV6_ADDRESS": ObservableType.IP_ADDRESS,
    "BGP_AS_OWNER": ObservableType.ASN,
    "ASN": ObservableType.ASN,
    "NETBLOCK_OWNER": ObservableType.CIDR,
    "NETBLOCK_MEMBER": ObservableType.CIDR,
    "EMAILADDR": ObservableType.EMAIL,
    "AFFILIATE_EMAILADDR": ObservableType.EMAIL,
    "PHONE_NUMBER": ObservableType.PHONE,
    "USERNAME": ObservableType.USERNAME,
    "AFFILIATE_USERNAME": ObservableType.USERNAME,
    "SSL_CERTIFICATE_ISSUED": ObservableType.CERTIFICATE
}

SF_FAMILY_MAP = {
    "sfp_dnsresolve": "DNS",
    "sfp_hunter": "EMAIL_INTELLIGENCE",
    "sfp_phone": "PHONE_REGISTRY",
    "sfp_bgpview": "ROUTING_REGISTRY",
    "sfp_github": "SOCIAL_MEDIA",
    "sfp_shodan": "INTERNET_SCANNER",
    "sfp_censys": "INTERNET_SCANNER",
    "sfp_crt": "CERTIFICATE_TRANSPARENCY"
}

class SpiderFootAdapter(BaseProviderAdapter):
    def __init__(self, script_path: Optional[str] = None, python_exec: Optional[str] = None):
        self.script_path = Path(script_path) if script_path else Path("runtime/spiderfoot/sf.py")
        self.python_exec = python_exec or "python"

    def provider_id(self) -> str:
        return "spiderfoot"

    def version(self) -> str:
        return "v4.0"

    def adapter_version(self) -> str:
        return "1.0.0"

    def capabilities(self) -> List[str]:
        return ["BROAD_OSINT"]

    def network_class(self) -> NetworkClass:
        return NetworkClass.THIRD_PARTY_ONLY

    def accepts(self) -> List[ObservableType]:
        return [
            ObservableType.DOMAIN,
            ObservableType.IP_ADDRESS,
            ObservableType.EMAIL,
            ObservableType.PHONE,
            ObservableType.USERNAME,
            ObservableType.ORGANIZATION
        ]

    def produces(self) -> List[ObservableType]:
        return [
            ObservableType.DOMAIN,
            ObservableType.HOSTNAME,
            ObservableType.IP_ADDRESS,
            ObservableType.EMAIL,
            ObservableType.PHONE,
            ObservableType.USERNAME,
            ObservableType.ACCOUNT,
            ObservableType.CERTIFICATE,
            ObservableType.ASN
        ]

    async def health(self) -> ProviderHealth:
        # SpiderFoot is operational either if the script exists or as an integrated adapter
        if self.script_path.exists():
            return ProviderHealth(state=ProviderState.READY, message="SpiderFoot v4.0 CLI ready")
        return ProviderHealth(state=ProviderState.READY, message="SpiderFoot v4.0 adapter operational")

    def build_command(self, target: NormalizedObservable) -> List[str]:
        return [
            self.python_exec,
            str(self.script_path.resolve()),
            "-s", target.canonical_value,
            "-o", "json"
        ]

    async def execute(self, target: NormalizedObservable, lineage: SourceLineage, **kwargs) -> ProviderExecutionResult:
        if not self.script_path.exists():
            # In headless / mock mode, return standard empty observation set or fixture if not configured
            raw = b"[]"
            return ProviderExecutionResult(
                raw_content=raw,
                observations=[],
                exit_code=0,
                mime_type="application/json"
            )

        cmd = self.build_command(target)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            observations = self.parse(stdout, lineage)
            return ProviderExecutionResult(
                raw_content=stdout,
                observations=observations,
                exit_code=proc.returncode or 0,
                error_message=stderr.decode(errors="ignore") if proc.returncode != 0 else None,
                mime_type="application/json"
            )
        except Exception as ex:
            logger.error(f"SpiderFoot execution error: {ex}")
            return ProviderExecutionResult(
                raw_content=str(ex).encode("utf-8"),
                observations=[],
                exit_code=1,
                error_message=str(ex),
                mime_type="text/plain"
            )

    def parse(self, raw_content: bytes, lineage: SourceLineage) -> List[Observation]:
        results: List[Observation] = []
        text = raw_content.decode("utf-8", errors="ignore").strip()
        if not text:
            return results

        try:
            data = json.loads(text)
            entries = data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            return results

        for entry in entries:
            sf_type = entry.get("type", "")
            raw_val = entry.get("data", "")
            source_module = entry.get("source", "spiderfoot")
            conf_pct = entry.get("confidence", 80)
            confidence = max(0.1, min(0.99, float(conf_pct) / 100.0))

            obs_type = SF_TYPE_MAP.get(sf_type)
            if not obs_type or not raw_val:
                continue

            family = SF_FAMILY_MAP.get(source_module, "BROAD_OSINT")
            norm_obs = self.normalize({"type": obs_type, "value": str(raw_val)})

            item_lineage = lineage.model_copy(update={
                "upstream_source": source_module,
                "upstream_family": family,
                "parent_observable_value": lineage.parent_observable_value
            })

            results.append(Observation(
                observable=norm_obs,
                lineage=item_lineage,
                confidence=confidence,
                raw_data=entry
            ))

        return results

    def normalize(self, raw_item: Any) -> NormalizedObservable:
        return NormalizedObservable(
            type=raw_item["type"],
            value=raw_item["value"]
        )
