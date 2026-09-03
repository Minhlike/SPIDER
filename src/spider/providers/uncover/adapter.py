import asyncio
import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from spider.providers.base import BaseProviderAdapter, ProviderHealth, ProviderExecutionResult
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage

logger = logging.getLogger(__name__)

UNCOVER_ENGINES = ["shodan", "censys", "fofa", "hunter", "zoomeye", "netlas", "criminalip"]

class UncoverAdapter(BaseProviderAdapter):
    def __init__(self, binary_path: Optional[str] = None):
        if binary_path:
            self.binary_path = Path(binary_path)
        else:
            self.binary_path = Path("tools/uncover/uncover.exe")

    def provider_id(self) -> str:
        return "uncover"

    def version(self) -> str:
        return "v1.2.1"

    def adapter_version(self) -> str:
        return "1.0.0"

    def capabilities(self) -> List[str]:
        return ["INTERNET_INTELLIGENCE"]

    def network_class(self) -> NetworkClass:
        return NetworkClass.THIRD_PARTY_ONLY

    def accepts(self) -> List[ObservableType]:
        return [ObservableType.DOMAIN, ObservableType.IP_ADDRESS, ObservableType.ORGANIZATION]

    def produces(self) -> List[ObservableType]:
        return [ObservableType.IP_ADDRESS, ObservableType.HOSTNAME, ObservableType.URL, ObservableType.CERTIFICATE]

    async def health(self) -> ProviderHealth:
        if not self.binary_path.exists():
            return ProviderHealth(
                state=ProviderState.BROKEN,
                message=f"Uncover binary not found at {self.binary_path}"
            )
        
        # Check if any API keys are configured in environment
        has_keys = any(
            os.environ.get(f"{eng.upper()}_API_KEY") or os.environ.get(f"{eng.upper()}_KEY")
            for eng in UNCOVER_ENGINES
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                str(self.binary_path.resolve()),
                "-version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=8.0)
            except asyncio.TimeoutError:
                try: proc.kill()
                except Exception: pass
                stdout, stderr = b"", b"Uncover timeout"
            if proc.returncode == 0 or b"v1.2.1" in stdout or b"v1.2.1" in stderr:
                if has_keys:
                    return ProviderHealth(state=ProviderState.READY, message="Uncover v1.2.1 operational with API keys")
                else:
                    return ProviderHealth(
                        state=ProviderState.MISSING_CREDENTIAL,
                        message="Uncover v1.2.1 operational (no search engine API keys configured)",
                        details={"supported_engines": UNCOVER_ENGINES}
                    )
            return ProviderHealth(state=ProviderState.DEGRADED, message=f"Version check returned {proc.returncode}")
        except Exception as e:
            return ProviderHealth(state=ProviderState.BROKEN, message=f"Health check failed: {str(e)}")

    def build_command(self, target: NormalizedObservable) -> List[str]:
        return [
            str(self.binary_path.resolve()),
            "-q", target.canonical_value,
            "-oJ",
            "-silent"
        ]

    def _has_keys(self) -> bool:
        return any(
            os.environ.get(f"{eng.upper()}_API_KEY") or os.environ.get(f"{eng.upper()}_KEY")
            for eng in UNCOVER_ENGINES
        )

    async def execute(self, target: NormalizedObservable, lineage: SourceLineage, **kwargs) -> ProviderExecutionResult:
        if not self._has_keys():
            return ProviderExecutionResult(
                raw_content=b"[]",
                observations=[],
                exit_code=0,
                error_message="No search engine API keys configured (MISSING_CREDENTIAL)",
                mime_type="application/json"
            )
        cmd = self.build_command(target)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=8.0)
            except asyncio.TimeoutError:
                try: proc.kill()
                except Exception: pass
                stdout, stderr = b"", b"Uncover timeout"
            observations = self.parse(stdout, lineage)
            return ProviderExecutionResult(
                raw_content=stdout,
                observations=observations,
                exit_code=proc.returncode or 0,
                error_message=stderr.decode(errors="ignore") if proc.returncode != 0 else None,
                mime_type="application/x-ndjson"
            )
        except Exception as ex:
            logger.error(f"Uncover execution error: {ex}")
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

            ip = data.get("ip")
            host = data.get("host")
            url = data.get("url")
            engine = data.get("engine", "uncover")
            family = "INTERNET_SCANNER"

            if ip:
                obs_ip = self.normalize({"type": ObservableType.IP_ADDRESS, "value": ip})
                item_lineage = lineage.model_copy(update={
                    "upstream_source": f"uncover_{engine}",
                    "upstream_family": family,
                    "parent_observable_value": lineage.parent_observable_value
                })
                results.append(Observation(
                    observable=obs_ip,
                    lineage=item_lineage,
                    confidence=0.9,
                    raw_data=data
                ))

            if host and host != ip:
                obs_host = self.normalize({"type": ObservableType.HOSTNAME, "value": host})
                item_lineage = lineage.model_copy(update={
                    "upstream_source": f"uncover_{engine}",
                    "upstream_family": family,
                    "parent_observable_value": ip or lineage.parent_observable_value
                })
                results.append(Observation(
                    observable=obs_host,
                    lineage=item_lineage,
                    confidence=0.85,
                    raw_data=data
                ))

            if url:
                obs_url = self.normalize({"type": ObservableType.URL, "value": url})
                item_lineage = lineage.model_copy(update={
                    "upstream_source": f"uncover_{engine}",
                    "upstream_family": family,
                    "parent_observable_value": ip or lineage.parent_observable_value
                })
                results.append(Observation(
                    observable=obs_url,
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
