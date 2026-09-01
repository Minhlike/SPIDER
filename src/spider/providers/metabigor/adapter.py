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

class MetabigorAdapter(BaseProviderAdapter):
    def __init__(self, binary_path: Optional[str] = None):
        if binary_path:
            self.binary_path = Path(binary_path)
        else:
            self.binary_path = Path("tools/metabigor/metabigor.exe")

    def provider_id(self) -> str:
        return "metabigor"

    def version(self) -> str:
        return "v2.2.0"

    def adapter_version(self) -> str:
        return "1.0.0"

    def capabilities(self) -> List[str]:
        return ["INFRASTRUCTURE_DISCOVERY"]

    def network_class(self) -> NetworkClass:
        return NetworkClass.THIRD_PARTY_ONLY

    def accepts(self) -> List[ObservableType]:
        return [ObservableType.IP_ADDRESS, ObservableType.DOMAIN, ObservableType.ASN, ObservableType.ORGANIZATION]

    def produces(self) -> List[ObservableType]:
        return [ObservableType.ASN, ObservableType.CIDR, ObservableType.ORGANIZATION, ObservableType.IP_ADDRESS]

    async def health(self) -> ProviderHealth:
        if not self.binary_path.exists():
            return ProviderHealth(
                state=ProviderState.BROKEN,
                message=f"Metabigor binary not found at {self.binary_path}"
            )
        try:
            proc = await asyncio.create_subprocess_exec(
                str(self.binary_path.resolve()),
                "version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0 or b"v2.2.0" in stdout:
                return ProviderHealth(state=ProviderState.READY, message="Metabigor v2.2.0 operational")
            return ProviderHealth(state=ProviderState.DEGRADED, message=f"Version check returned {proc.returncode}")
        except Exception as e:
            return ProviderHealth(state=ProviderState.BROKEN, message=f"Health check failed: {str(e)}")

    def build_command(self, target: NormalizedObservable) -> List[str]:
        val = target.canonical_value
        return [
            str(self.binary_path.resolve()),
            "net",
            val,
            "-f", "json",
            "-q"
        ]

    async def execute(self, target: NormalizedObservable, lineage: SourceLineage, **kwargs) -> ProviderExecutionResult:
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
            logger.error(f"Metabigor execution error: {ex}")
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
            # Try ndjson or line-based format
            entries = []
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    # fallback plain text line parsing
                    entries.append({"cidr": line})

        for entry in entries:
            asn = entry.get("asn") or entry.get("ASN")
            org = entry.get("org") or entry.get("Org") or entry.get("organization")
            cidr = entry.get("cidr") or entry.get("CIDR") or entry.get("range")
            source = entry.get("source", "metabigor_bgp")
            family = "ROUTING_REGISTRY"

            if asn:
                obs_asn = self.normalize({"type": ObservableType.ASN, "value": str(asn)})
                item_lineage = lineage.model_copy(update={
                    "upstream_source": source,
                    "upstream_family": family,
                    "parent_observable_value": lineage.parent_observable_value
                })
                results.append(Observation(
                    observable=obs_asn,
                    lineage=item_lineage,
                    confidence=0.95,
                    raw_data=entry
                ))

            if org:
                obs_org = self.normalize({"type": ObservableType.ORGANIZATION, "value": str(org)})
                item_lineage = lineage.model_copy(update={
                    "upstream_source": source,
                    "upstream_family": family,
                    "parent_observable_value": str(asn) if asn else lineage.parent_observable_value
                })
                results.append(Observation(
                    observable=obs_org,
                    lineage=item_lineage,
                    confidence=0.9,
                    raw_data=entry
                ))

            if cidr:
                obs_cidr = self.normalize({"type": ObservableType.CIDR, "value": str(cidr)})
                item_lineage = lineage.model_copy(update={
                    "upstream_source": source,
                    "upstream_family": family,
                    "parent_observable_value": str(asn) if asn else lineage.parent_observable_value
                })
                results.append(Observation(
                    observable=obs_cidr,
                    lineage=item_lineage,
                    confidence=0.9,
                    raw_data=entry
                ))

        return results

    def normalize(self, raw_item: Any) -> NormalizedObservable:
        return NormalizedObservable(
            type=raw_item["type"],
            value=raw_item["value"]
        )
