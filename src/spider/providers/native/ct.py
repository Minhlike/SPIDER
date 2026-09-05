import asyncio
import json
import logging
import urllib.request
import urllib.parse
import httpx
from spider.providers.transport import provider_client
from typing import List, Dict, Any, Optional
from spider.providers.base import BaseProviderAdapter, ProviderHealth, ProviderExecutionResult
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage

logger = logging.getLogger(__name__)

class NativeCertificateTransparencyAdapter(BaseProviderAdapter):
    request_budget_supported = True
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
        try:
            async with provider_client(self.provider_id(), kwargs, timeout=3,
                                       follow_redirects=True) as client:
                response = await client.get("https://crt.sh/", params={"q": domain, "output": "json"})
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, list):
                    raise ValueError("Invalid response shape")
            raw_bytes = json.dumps(data, indent=2).encode("utf-8")
            observations = self.parse(raw_bytes, lineage)
            return ProviderExecutionResult(
                raw_content=raw_bytes,
                observations=observations,
                exit_code=0,
                mime_type="application/json"
            )
        except (httpx.HTTPError, ValueError):
            return ProviderExecutionResult(
                raw_content=b"",
                observations=[],
                exit_code=1,
                error_message="Certificate transparency response unavailable or invalid",
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
            if len(results) >= 50:
                break
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
