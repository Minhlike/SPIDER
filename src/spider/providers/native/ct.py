import asyncio
import json
import logging
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Optional
from spider.providers.base import BaseProviderAdapter, ProviderHealth, ProviderExecutionResult
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage

logger = logging.getLogger(__name__)

class NativeCertificateTransparencyAdapter(BaseProviderAdapter):
    def provider_id(self) -> str:
        return "native_ct"

    def version(self) -> str:
        return "1.0.0"

    def adapter_version(self) -> str:
        return "1.0.0"

    def capabilities(self) -> List[str]:
        return ["CERTIFICATE_TRANSPARENCY", "SUBDOMAIN_DISCOVERY"]

    def network_class(self) -> NetworkClass:
        return NetworkClass.THIRD_PARTY_ONLY

    def accepts(self) -> List[ObservableType]:
        return [ObservableType.DOMAIN]

    def produces(self) -> List[ObservableType]:
        return [ObservableType.HOSTNAME, ObservableType.CERTIFICATE]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            state=ProviderState.READY,
            message="Native Certificate Transparency (crt.sh) client operational"
        )

    def build_command(self, target: NormalizedObservable) -> List[str]:
        return ["internal", "ct_query", target.canonical_value]

    async def execute(self, target: NormalizedObservable, lineage: SourceLineage, **kwargs) -> ProviderExecutionResult:
        domain = target.canonical_value
        loop = asyncio.get_running_loop()

        def _fetch_ct_sync() -> List[Dict[str, Any]]:
            url = f"https://crt.sh/?q=%25.{urllib.parse.quote(domain)}&output=json"
            req = urllib.request.Request(url, headers={"User-Agent": "SPIDER-OSINT/2.0"})
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read().decode("utf-8", errors="ignore"))
            except Exception:
                return []

        try:
            data = await loop.run_in_executor(None, _fetch_ct_sync)
            raw_bytes = json.dumps(data, indent=2).encode("utf-8")
            observations = self.parse(raw_bytes, lineage)
            return ProviderExecutionResult(
                raw_content=raw_bytes,
                observations=observations,
                exit_code=0,
                mime_type="application/json"
            )
        except Exception as ex:
            logger.error(f"CT query error: {ex}")
            return ProviderExecutionResult(
                raw_content=str(ex).encode("utf-8"),
                observations=[],
                exit_code=1,
                error_message=str(ex),
                mime_type="text/plain"
            )

    def parse(self, raw_content: bytes, lineage: SourceLineage) -> List[Observation]:
        results: List[Observation] = []
        try:
            entries = json.loads(raw_content.decode("utf-8"))
        except Exception:
            return results

        seen_hosts = set()
        for item in entries:
            name_value = item.get("name_value", "")
            for raw_host in name_value.splitlines():
                host = raw_host.strip().lower()
                if host.startswith("*."):
                    host = host[2:]
                if not host or host in seen_hosts or "." not in host:
                    continue
                seen_hosts.add(host)

                obs = self.normalize({"type": ObservableType.HOSTNAME, "value": host})
                item_lineage = lineage.model_copy(update={
                    "upstream_source": "crt_sh",
                    "upstream_family": "CERTIFICATE_TRANSPARENCY",
                    "parent_observable_value": lineage.parent_observable_value
                })
                results.append(Observation(
                    observable=obs,
                    lineage=item_lineage,
                    confidence=0.90,
                    raw_data=item
                ))

        return results

    def normalize(self, raw_item: Any) -> NormalizedObservable:
        return NormalizedObservable(
            type=raw_item["type"],
            value=raw_item["value"]
        )
