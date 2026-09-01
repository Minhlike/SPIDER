import asyncio
import json
import logging
from typing import List, Dict, Any, Optional
import dns.resolver
import dns.reversename
from spider.providers.base import BaseProviderAdapter, ProviderHealth, ProviderExecutionResult
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage

logger = logging.getLogger(__name__)

class NativeDnsAdapter(BaseProviderAdapter):
    def provider_id(self) -> str:
        return "native_dns"

    def version(self) -> str:
        return "1.0.0"

    def adapter_version(self) -> str:
        return "1.0.0"

    def capabilities(self) -> List[str]:
        return ["DNS_ENUMERATION", "MAIL_INFRASTRUCTURE"]

    def network_class(self) -> NetworkClass:
        return NetworkClass.THIRD_PARTY_ONLY

    def accepts(self) -> List[ObservableType]:
        return [ObservableType.DOMAIN, ObservableType.HOSTNAME, ObservableType.EMAIL, ObservableType.IP_ADDRESS]

    def produces(self) -> List[ObservableType]:
        return [ObservableType.IP_ADDRESS, ObservableType.IPV6_ADDRESS, ObservableType.HOSTNAME, ObservableType.DOMAIN]

    async def health(self) -> ProviderHealth:
        try:
            resolver = dns.resolver.Resolver()
            resolver.lifetime = 2.0
            return ProviderHealth(
                state=ProviderState.READY,
                message="Native dnspython DNS resolver operational"
            )
        except Exception as e:
            return ProviderHealth(state=ProviderState.BROKEN, message=f"DNS health check failed: {e}")

    def build_command(self, target: NormalizedObservable) -> List[str]:
        return ["internal", "dns_lookup", target.canonical_value]

    async def execute(self, target: NormalizedObservable, lineage: SourceLineage, **kwargs) -> ProviderExecutionResult:
        val = target.canonical_value.strip()
        obs_type = target.type
        results_data: Dict[str, Any] = {"target": val, "type": obs_type.value, "records": []}

        # If EMAIL, extract domain
        query_domain = val
        if obs_type == ObservableType.EMAIL and "@" in val:
            query_domain = val.split("@")[1].strip()

        loop = asyncio.get_running_loop()

        def _resolve_sync() -> Dict[str, Any]:
            records = []
            res = dns.resolver.Resolver()
            res.lifetime = 4.0
            res.timeout = 4.0

            # 1. Reverse DNS (PTR) for IP
            if obs_type in (ObservableType.IP_ADDRESS, ObservableType.IPV6_ADDRESS):
                try:
                    rev_name = dns.reversename.from_address(val)
                    answers = res.resolve(rev_name, "PTR")
                    for r in answers:
                        records.append({"type": "PTR", "value": str(r).rstrip(".")})
                except Exception:
                    pass
                return {"target": val, "records": records}

            # 2. Forward DNS (A, AAAA, MX, NS, TXT, CNAME, SOA)
            for rtype in ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]:
                try:
                    answers = res.resolve(query_domain, rtype)
                    for rdata in answers:
                        if rtype == "MX":
                            records.append({"type": "MX", "value": str(rdata.exchange).rstrip("."), "preference": rdata.preference})
                        elif rtype in ("NS", "CNAME"):
                            records.append({"type": rtype, "value": str(rdata).rstrip(".")})
                        elif rtype == "TXT":
                            records.append({"type": "TXT", "value": str(rdata)})
                        else:
                            records.append({"type": rtype, "value": str(rdata)})
                except Exception:
                    pass

            return {"target": val, "query_domain": query_domain, "records": records}

        try:
            results_data = await loop.run_in_executor(None, _resolve_sync)
            raw_bytes = json.dumps(results_data, indent=2).encode("utf-8")
            observations = self.parse(raw_bytes, lineage)
            return ProviderExecutionResult(
                raw_content=raw_bytes,
                observations=observations,
                exit_code=0,
                mime_type="application/json"
            )
        except Exception as ex:
            logger.error(f"Native DNS error: {ex}")
            err_bytes = str(ex).encode("utf-8")
            return ProviderExecutionResult(
                raw_content=err_bytes,
                observations=[],
                exit_code=1,
                error_message=str(ex),
                mime_type="text/plain"
            )

    def parse(self, raw_content: bytes, lineage: SourceLineage) -> List[Observation]:
        results: List[Observation] = []
        try:
            data = json.loads(raw_content.decode("utf-8"))
        except Exception:
            return results

        target_val = data.get("target", "")
        query_domain = data.get("query_domain", target_val)
        records = data.get("records", [])

        # If Target was EMAIL, create DOMAIN observation
        if "@" in target_val:
            domain_obs = self.normalize({"type": ObservableType.DOMAIN, "value": query_domain})
            dom_lineage = lineage.model_copy(update={
                "upstream_source": "native_dns_email_decomposer",
                "upstream_family": "DNS",
                "parent_observable_value": target_val
            })
            results.append(Observation(
                observable=domain_obs,
                lineage=dom_lineage,
                confidence=0.99,
                raw_data={"email": target_val, "extracted_domain": query_domain}
            ))

        for rec in records:
            rtype = rec.get("type")
            rval = rec.get("value")
            if not rval:
                continue

            item_lineage = lineage.model_copy(update={
                "upstream_source": f"dns_{rtype.lower()}",
                "upstream_family": "DNS",
                "parent_observable_value": query_domain
            })

            if rtype == "A":
                obs = self.normalize({"type": ObservableType.IP_ADDRESS, "value": rval})
                results.append(Observation(observable=obs, lineage=item_lineage, confidence=0.95, raw_data=rec))
            elif rtype == "AAAA":
                obs = self.normalize({"type": ObservableType.IPV6_ADDRESS, "value": rval})
                results.append(Observation(observable=obs, lineage=item_lineage, confidence=0.95, raw_data=rec))
            elif rtype in ("MX", "NS", "PTR", "CNAME"):
                obs = self.normalize({"type": ObservableType.HOSTNAME, "value": rval})
                results.append(Observation(observable=obs, lineage=item_lineage, confidence=0.95, raw_data=rec))

        return results

    def normalize(self, raw_item: Any) -> NormalizedObservable:
        return NormalizedObservable(
            type=raw_item["type"],
            value=raw_item["value"]
        )
