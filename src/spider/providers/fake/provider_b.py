import json
from typing import List, Dict, Any
from spider.providers.base import BaseProviderAdapter, ProviderHealth, ProviderExecutionResult
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage

class FakeProviderB(BaseProviderAdapter):
    request_budget_supported = True  # Offline synthetic data, no network I/O.
    """
    Fake Provider B: Simulates Infrastructure Discovery (e.g. Metabigor).
    Accepts: IP_ADDRESS, DOMAIN
    Produces: ASN, CIDR, ORGANIZATION
    """
    def provider_id(self) -> str:
        return "fake_b"

    def version(self) -> str:
        return "1.0.0"

    def adapter_version(self) -> str:
        return "1.0.0"

    def capabilities(self) -> List[str]:
        return ["INFRASTRUCTURE_DISCOVERY"]

    def network_class(self) -> NetworkClass:
        return NetworkClass.THIRD_PARTY_ONLY

    def accepts(self) -> List[ObservableType]:
        return [ObservableType.IP_ADDRESS, ObservableType.DOMAIN]

    def produces(self) -> List[ObservableType]:
        return [ObservableType.ASN, ObservableType.CIDR, ObservableType.ORGANIZATION]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(state=ProviderState.READY, message="FakeProviderB operational")

    def build_command(self, target: NormalizedObservable) -> List[str]:
        return ["fake_b.exe", "net", "-t", target.canonical_value]

    async def execute(self, target: NormalizedObservable, lineage: SourceLineage, **kwargs) -> ProviderExecutionResult:
        val = target.canonical_value
        items = [
            {"asn": "AS15133", "org": "EdgeCast Networks", "cidr": "93.184.216.0/24", "source": "bgpview", "family": "ROUTING_REGISTRY"}
        ]
        raw_bytes = json.dumps(items, indent=2).encode("utf-8")
        observations = self.parse(raw_bytes, lineage)
        return ProviderExecutionResult(
            raw_content=raw_bytes,
            observations=observations,
            exit_code=0,
            mime_type="application/json"
        )

    def parse(self, raw_content: bytes, lineage: SourceLineage) -> List[Observation]:
        data = json.loads(raw_content.decode("utf-8"))
        results: List[Observation] = []
        for entry in data:
            asn = entry.get("asn")
            org = entry.get("org")
            cidr = entry.get("cidr")
            family = entry.get("family", "ROUTING_REGISTRY")
            source = entry.get("source", "bgpview")

            if asn:
                obs_asn = self.normalize({"type": ObservableType.ASN, "value": asn})
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
                obs_org = self.normalize({"type": ObservableType.ORGANIZATION, "value": org})
                item_lineage = lineage.model_copy(update={
                    "upstream_source": source,
                    "upstream_family": family,
                    "parent_observable_value": asn or lineage.parent_observable_value,
                    "parent_observable_type": ObservableType.ASN if asn else lineage.parent_observable_type,
                    "parent_namespace": "" if asn else lineage.parent_namespace,
                })
                results.append(Observation(
                    observable=obs_org,
                    lineage=item_lineage,
                    confidence=0.9,
                    raw_data=entry
                ))

            if cidr:
                obs_cidr = self.normalize({"type": ObservableType.CIDR, "value": cidr})
                item_lineage = lineage.model_copy(update={
                    "upstream_source": source,
                    "upstream_family": family,
                    "parent_observable_value": lineage.parent_observable_value
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
