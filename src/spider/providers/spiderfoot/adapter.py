import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from spider.providers.base import BaseProviderAdapter, ProviderHealth, ProviderExecutionResult
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage

logger = logging.getLogger(__name__)

SF_TYPE_MAP: Dict[str, ObservableType] = {
    "IP_ADDRESS": ObservableType.IP_ADDRESS,
    "IP Address": ObservableType.IP_ADDRESS,
    "IPV6_ADDRESS": ObservableType.IPV6_ADDRESS,
    "IPv6 Address": ObservableType.IPV6_ADDRESS,
    "DOMAIN_NAME": ObservableType.DOMAIN,
    "Domain Name": ObservableType.DOMAIN,
    "INTERNET_NAME": ObservableType.HOSTNAME,
    "Internet Name": ObservableType.HOSTNAME,
    "AFFILIATE_INTERNET_NAME": ObservableType.HOSTNAME,
    "AFFILIATE_DOMAIN_NAME": ObservableType.DOMAIN,
    "EMAILADDR": ObservableType.EMAIL,
    "Email Address": ObservableType.EMAIL,
    "PHONE_NUMBER": ObservableType.PHONE,
    "Phone Number": ObservableType.PHONE,
    "USERNAME": ObservableType.USERNAME,
    "Username": ObservableType.USERNAME,
    "HUMAN_NAME": ObservableType.ORGANIZATION,
    "Human Name": ObservableType.ORGANIZATION,
    "BGP_AS_OWNER": ObservableType.ORGANIZATION,
    "BGP AS Owner": ObservableType.ORGANIZATION,
    "BGP_AS_MEMBER": ObservableType.ASN,
    "BGP AS Member": ObservableType.ASN,
    "NETBLOCK_MEMBER": ObservableType.CIDR,
    "Netblock Member": ObservableType.CIDR,
    "ACCOUNT_EXTERNAL_OWNED": ObservableType.ACCOUNT,
    "Account External Owned": ObservableType.ACCOUNT
}

SF_MODULE_PROFILES: Dict[str, List[str]] = {
    "SF_DOMAIN_PUBLIC": ["sfp_dnsresolve", "sfp_whois", "sfp_threatcrowd", "sfp_crt", "sfp_hackertarget", "sfp_securitytrails_passive"],
    "SF_IP_PUBLIC": ["sfp_dnsresolve", "sfp_whois", "sfp_bgpview", "sfp_cymru"],
    "SF_EMAIL_PUBLIC": ["sfp_dnsresolve", "sfp_whois", "sfp_mailgun", "sfp_hunter_free"],
    "SF_USERNAME_PUBLIC": ["sfp_accounts", "sfp_github", "sfp_pastebin"],
    "SF_PHONE_PUBLIC": ["sfp_phonenumbers", "sfp_numverify_free"]
}

class SpiderFootAdapter(BaseProviderAdapter):
    def __init__(self, sf_script: Optional[str] = None, python_exec: Optional[str] = None):
        self.sf_script = Path(sf_script) if sf_script else Path("tools/spiderfoot/sf.py")
        self.python_exec = python_exec or sys.executable or "python"

    def provider_id(self) -> str:
        return "spiderfoot"

    def version(self) -> str:
        return "v4.0.0"

    def adapter_version(self) -> str:
        return "2.0.0"

    def capabilities(self) -> List[str]:
        return ["BROAD_OSINT", "SUBDOMAIN_DISCOVERY", "MAIL_INFRASTRUCTURE", "REGISTRY_LOOKUP"]

    def network_class(self) -> NetworkClass:
        return NetworkClass.THIRD_PARTY_ONLY

    def accepts(self) -> List[ObservableType]:
        return [
            ObservableType.DOMAIN,
            ObservableType.HOSTNAME,
            ObservableType.IP_ADDRESS,
            ObservableType.EMAIL,
            ObservableType.USERNAME,
            ObservableType.PHONE
        ]

    def produces(self) -> List[ObservableType]:
        return [
            ObservableType.HOSTNAME,
            ObservableType.IP_ADDRESS,
            ObservableType.IPV6_ADDRESS,
            ObservableType.EMAIL,
            ObservableType.ORGANIZATION,
            ObservableType.ASN,
            ObservableType.CIDR,
            ObservableType.ACCOUNT
        ]

    async def health(self) -> ProviderHealth:
        if not self.sf_script.exists():
            return ProviderHealth(
                state=ProviderState.MISSING_RUNTIME,
                runtime_path=str(self.sf_script),
                runtime_exists=False,
                runtime_version_verified=False,
                message=f"SpiderFoot sf.py not found at {self.sf_script}"
            )

        start_t = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                self.python_exec,
                str(self.sf_script.resolve()),
                "-V",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            latency = (time.perf_counter() - start_t) * 1000
            out_str = stdout.decode(errors="ignore") + stderr.decode(errors="ignore")
            if proc.returncode == 0 or "SpiderFoot" in out_str:
                return ProviderHealth(
                    state=ProviderState.READY,
                    provider_version="4.0.0",
                    runtime_path=str(self.sf_script.resolve()),
                    runtime_exists=True,
                    runtime_version_verified=True,
                    latency_ms=latency,
                    message="SpiderFoot v4.0.0 CLI runtime operational on Windows"
                )
            return ProviderHealth(
                state=ProviderState.DEGRADED,
                runtime_path=str(self.sf_script),
                message=f"SpiderFoot -V returned code {proc.returncode}"
            )
        except Exception as e:
            return ProviderHealth(
                state=ProviderState.BROKEN,
                runtime_path=str(self.sf_script),
                message=f"SpiderFoot health check error: {str(e)}"
            )

    def select_modules(self, target_type: ObservableType) -> str:
        if target_type in (ObservableType.DOMAIN, ObservableType.HOSTNAME):
            return ",".join(SF_MODULE_PROFILES["SF_DOMAIN_PUBLIC"])
        elif target_type in (ObservableType.IP_ADDRESS, ObservableType.IPV6_ADDRESS):
            return ",".join(SF_MODULE_PROFILES["SF_IP_PUBLIC"])
        elif target_type == ObservableType.EMAIL:
            return ",".join(SF_MODULE_PROFILES["SF_EMAIL_PUBLIC"])
        elif target_type == ObservableType.USERNAME:
            return ",".join(SF_MODULE_PROFILES["SF_USERNAME_PUBLIC"])
        elif target_type == ObservableType.PHONE:
            return ",".join(SF_MODULE_PROFILES["SF_PHONE_PUBLIC"])
        return "sfp_dnsresolve,sfp_whois"

    def build_command(self, target: NormalizedObservable) -> List[str]:
        modules = self.select_modules(target.type)
        return [
            self.python_exec,
            str(self.sf_script.resolve()),
            "-s", target.canonical_value,
            "-m", modules,
            "-u", "passive",
            "-o", "json",
            "-q"
        ]

    async def execute(self, target: NormalizedObservable, lineage: SourceLineage, **kwargs) -> ProviderExecutionResult:
        if not self.sf_script.exists():
            return ProviderExecutionResult(
                raw_content=b"SpiderFoot runtime missing",
                observations=[],
                exit_code=1,
                error_message="SpiderFoot sf.py not found on disk",
                mime_type="text/plain"
            )

        cmd = self.build_command(target)
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        start_t = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=25.0)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                return ProviderExecutionResult(
                    raw_content=b"SpiderFoot task timed out",
                    observations=[],
                    exit_code=124,
                    error_message="SpiderFoot task timed out after 25s",
                    mime_type="text/plain"
                )
            duration = (time.perf_counter() - start_t) * 1000
            observations = self.parse(stdout, lineage)
            return ProviderExecutionResult(
                raw_content=stdout,
                observations=observations,
                exit_code=proc.returncode or 0,
                error_message=stderr.decode(errors="ignore") if proc.returncode != 0 else None,
                mime_type="application/json",
                duration_ms=duration,
                raw_items_count=len(observations),
                accepted_count=len(observations)
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

        # Process lines (SpiderFoot outputs stream of json objects)
        for raw_line in text.splitlines():
            line = raw_line.strip().rstrip(",")
            if line.endswith("[]"):
                line = line[:-2].strip().rstrip(",")
            if not line or line in ("[]", "[", "]"):
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(entry, dict):
                continue

            sf_type = entry.get("type", "")
            raw_val = entry.get("data", "")
            module_name = entry.get("module") or entry.get("source") or "spiderfoot"
            parent_src = entry.get("source") if entry.get("module") else lineage.parent_observable_value

            obs_type = SF_TYPE_MAP.get(sf_type)
            if not obs_type or not raw_val:
                continue

            # Family classification based on real module name
            family = "DNS" if "dns" in module_name.lower() else (
                "ROUTING_REGISTRY" if ("whois" in module_name.lower() or "bgp" in module_name.lower()) else (
                    "CERTIFICATE_TRANSPARENCY" if "crt" in module_name.lower() else "SECURITY_INTELLIGENCE"
                )
            )

            norm_obs = self.normalize({"type": obs_type, "value": str(raw_val)})
            item_lineage = lineage.model_copy(update={
                "upstream_source": f"sf_{module_name}",
                "upstream_family": family,
                "parent_observable_value": str(parent_src)
            })

            results.append(Observation(
                observable=norm_obs,
                lineage=item_lineage,
                confidence=0.85,
                raw_data=entry
            ))

        return results

    def normalize(self, raw_item: Any) -> NormalizedObservable:
        return NormalizedObservable(
            type=raw_item["type"],
            value=raw_item["value"]
        )
