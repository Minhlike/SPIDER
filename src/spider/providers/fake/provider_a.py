import json
from typing import List, Dict, Any
from spider.providers.base import BaseProviderAdapter, ProviderHealth, ProviderExecutionResult
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage

class FakeProviderA(BaseProviderAdapter):
    request_budget_supported = True  # Offline synthetic data, no network I/O.
    """
    Fake Provider A: Simulates Subdomain Discovery (e.g. Subfinder).
    Accepts: DOMAIN
    Produces: HOSTNAME, IP_ADDRESS
    """
    def provider_id(self) -> str:
        return "fake_a"

    def version(self) -> str:
        return "1.0.0"

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
        return ProviderHealth(state=ProviderState.READY, message="FakeProviderA operational")

    def build_command(self, target: NormalizedObservable) -> List[str]:
        return ["fake_a.exe", "-d", target.canonical_value]

    async def execute(self, target: NormalizedObservable, lineage: SourceLineage, **kwargs) -> ProviderExecutionResult:
        domain = target.canonical_value
        # Generate deterministic mock items
        items = [
            {"host": f"api.{domain}", "ip": "93.184.216.34", "source": "crt.sh", "family": "CERTIFICATE_TRANSPARENCY"},
            {"host": f"admin.{domain}", "ip": "93.184.216.35", "source": "virustotal", "family": "SECURITY_INTELLIGENCE"},
            {"host": f"mail.{domain}", "ip": "93.184.216.36", "source": "dnsdumpster", "family": "DNS"}
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
            host = entry.get("host")
            ip = entry.get("ip")
            family = entry.get("family", "CERTIFICATE_TRANSPARENCY")
            source = entry.get("source", "crtsh")

            if host:
                obs_host = self.normalize({"type": ObservableType.HOSTNAME, "value": host})
                item_lineage = lineage.model_copy(update={
                    "upstream_source": source,
                    "upstream_family": family,
                    "parent_observable_value": lineage.parent_observable_value
                })
                results.append(Observation(
                    observable=obs_host,
                    lineage=item_lineage,
                    confidence=0.9,
                    raw_data=entry
                ))

            if ip:
                obs_ip = self.normalize({"type": ObservableType.IP_ADDRESS, "value": ip})
                item_lineage = lineage.model_copy(update={
                    "upstream_source": source,
                    "upstream_family": family,
                    "parent_observable_value": host or lineage.parent_observable_value,
                    "parent_observable_type": ObservableType.HOSTNAME if host else lineage.parent_observable_type,
                    "parent_namespace": "" if host else lineage.parent_namespace,
                })
                results.append(Observation(
                    observable=obs_ip,
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
