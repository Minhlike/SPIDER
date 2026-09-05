import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from spider.providers.base import BaseProviderAdapter, ProviderHealth, ProviderExecutionResult
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage

logger = logging.getLogger(__name__)

SOURCE_FAMILY_MAP = {
    "crtsh": "CERTIFICATE_TRANSPARENCY",
    "certspotter": "CERTIFICATE_TRANSPARENCY",
    "censys": "INTERNET_SCANNER",
    "shodan": "INTERNET_SCANNER",
    "virustotal": "SECURITY_INTELLIGENCE",
    "alienvault": "SECURITY_INTELLIGENCE",
    "securitytrails": "SECURITY_INTELLIGENCE",
    "dnsdumpster": "DNS",
    "hackertarget": "WEB_SCRAPER",
    "threatcrowd": "SECURITY_INTELLIGENCE"
}

class SubfinderAdapter(BaseProviderAdapter):
    def __init__(self, binary_path: Optional[str] = None):
        if binary_path:
            self.binary_path = Path(binary_path)
        else:
            self.binary_path = Path("tools/subfinder/subfinder.exe")

    def provider_id(self) -> str:
        return "subfinder"

    def version(self) -> str:
        return "v2.16.0"

    def adapter_version(self) -> str:
        return "1.0.0"

    def capabilities(self) -> List[str]:
        return ["SUBDOMAIN_DISCOVERY"]

    def network_class(self) -> NetworkClass:
        return NetworkClass.THIRD_PARTY_ONLY

    def accepts(self) -> List[ObservableType]:
        return [ObservableType.DOMAIN]

    def produces(self) -> List[ObservableType]:
        return [ObservableType.HOSTNAME, ObservableType.IP_ADDRESS]

    async def health(self) -> ProviderHealth:
        if not self.binary_path.exists():
            return ProviderHealth(
                state=ProviderState.BROKEN,
                message=f"Subfinder binary not found at {self.binary_path}"
            )
        try:
            proc = await asyncio.create_subprocess_exec(
                str(self.binary_path.resolve()),
                "-version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            except asyncio.TimeoutError:
                try: proc.kill()
                except Exception: pass
                stdout, stderr = b"", b"Subfinder timeout"
            if proc.returncode == 0 or b"v2.16.0" in stdout or b"v2.16.0" in stderr:
                return ProviderHealth(state=ProviderState.READY, message="Subfinder v2.16.0 operational")
            return ProviderHealth(state=ProviderState.DEGRADED, message=f"Unexpected version check output: {stderr.decode()}")
        except Exception as e:
            return ProviderHealth(state=ProviderState.BROKEN, message=f"Health check failed: {str(e)}")

    def build_command(self, target: NormalizedObservable) -> List[str]:
        return [
            str(self.binary_path.resolve()),
            "-d", target.canonical_value,
            "-s", "hackertarget,alienvault",
            "-oJ",
            "-silent",
            "-timeout", "4"
        ]

    async def execute(self, target: NormalizedObservable, lineage: SourceLineage, **kwargs) -> ProviderExecutionResult:
        cmd = self.build_command(target)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            except asyncio.TimeoutError:
                try: proc.kill()
                except Exception: pass
                stdout, stderr = b"", b"Subfinder timeout"
            
            if proc.returncode != 0:
                logger.warning(f"Subfinder exited with code {proc.returncode}: {stderr.decode(errors='ignore')}")
            
            observations = self.parse(stdout, lineage)
            return ProviderExecutionResult(
                raw_content=stdout,
                observations=observations,
                exit_code=proc.returncode or 0,
                error_message=stderr.decode(errors="ignore") if proc.returncode != 0 else None,
                mime_type="application/x-ndjson"
            )
        except Exception as ex:
            logger.error(f"Subfinder execution error: {ex}")
            return ProviderExecutionResult(
                raw_content=str(ex).encode("utf-8"),
                observations=[],
                exit_code=1,
                error_message=str(ex),
                mime_type="text/plain"
            )

    def parse(self, raw_content: bytes, lineage: SourceLineage) -> List[Observation]:
        results: List[Observation] = []
        text = raw_content.decode("utf-8", errors="ignore")
        
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            host = data.get("host")
            ip = data.get("ip")
            sources = data.get("sources", [])
            primary_source = sources[0] if sources else "subfinder_passive"
            family = SOURCE_FAMILY_MAP.get(primary_source.lower(), "THIRD_PARTY_PASSIVE")

            if host:
                obs_host = self.normalize({"type": ObservableType.HOSTNAME, "value": host})
                item_lineage = lineage.model_copy(update={
                    "upstream_source": primary_source,
                    "upstream_family": family,
                    "parent_observable_value": lineage.parent_observable_value
                })
                results.append(Observation(
                    observable=obs_host,
                    lineage=item_lineage,
                    confidence=0.9,
                    raw_data=data
                ))

            if ip:
                obs_ip = self.normalize({"type": ObservableType.IP_ADDRESS, "value": ip})
                item_lineage = lineage.model_copy(update={
                    "upstream_source": primary_source,
                    "upstream_family": family,
                    "parent_observable_value": host or lineage.parent_observable_value,
                    "parent_observable_type": ObservableType.HOSTNAME if host else lineage.parent_observable_type,
                    "parent_namespace": "" if host else lineage.parent_namespace,
                })
                results.append(Observation(
                    observable=obs_ip,
                    lineage=item_lineage,
                    confidence=0.85,
                    raw_data=data
                ))

        return results

    def normalize(self, raw_item: Any) -> NormalizedObservable:
        return NormalizedObservable(
            type=raw_item["type"],
            value=raw_item["value"]
        )
