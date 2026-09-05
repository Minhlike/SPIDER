import asyncio
import json
import logging
from typing import List, Dict, Any, Optional
import dns.resolver
import dns.reversename
import dns.asyncquery
import dns.message
import dns.flags
import dns.rcode
from spider.models.budget import RequestBudgetExceeded
from spider.providers.base import BaseProviderAdapter, ProviderHealth, ProviderExecutionResult
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage

logger = logging.getLogger(__name__)

class NativeDnsAdapter(BaseProviderAdapter):
    request_budget_supported = True
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

        records, incomplete = [], False
        ledger, budget = kwargs.get("request_ledger"), kwargs.get("execution_budget")
        recorder = kwargs.get("egress_recorder")
        resolver = dns.resolver.Resolver()
        reverse = obs_type in (ObservableType.IP_ADDRESS, ObservableType.IPV6_ADDRESS)
        query_name = dns.reversename.from_address(val) if reverse else query_domain
        disclosed = NormalizedObservable(type=ObservableType.DOMAIN, value=query_domain) if obs_type == ObservableType.EMAIL else target
        async def dispatch(query, address, tcp=False):
            protocol = "tcp_fallback" if tcp else "udp"
            if ledger is not None:
                ledger.request(budget, self.provider_id(), "DNS", protocol)
            event = await recorder.begin(address, "dns_" + protocol, identifier=disclosed) if recorder else None
            try:
                response = await (dns.asyncquery.tcp if tcp else dns.asyncquery.udp)(query, address, timeout=4)
            except BaseException:
                if event:
                    await recorder.finish(event, "UNKNOWN_AFTER_DISPATCH")
                raise
            if event:
                await recorder.finish(event, "DNS_" + dns.rcode.to_text(response.rcode()))
            return response
        for rtype in (["PTR"] if reverse else ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]):
            query = dns.message.make_query(query_name, rtype)
            response = None
            try:
                # Explicit attempts: no resolver cache, search suffixes, or hidden retries.
                for nameserver in resolver.nameservers:
                    address = nameserver if isinstance(nameserver, str) else getattr(nameserver, "address", None)
                    if not address:
                        continue
                    try:
                        response = await dispatch(query, address)
                        if response.flags & dns.flags.TC:
                            response = await dispatch(query, address, tcp=True)
                        if response.rcode() in (dns.rcode.NOERROR, dns.rcode.NXDOMAIN):
                            break
                        response = None
                    except (dns.exception.DNSException, OSError):
                        response = None
                if response is None:
                    incomplete = True
                    continue
                for rrset in response.answer:
                    if rrset.rdtype != dns.rdatatype.from_text(rtype):
                        continue
                    for rdata in rrset:
                        if rtype == "MX":
                            records.append({"type": rtype, "value": str(rdata.exchange).rstrip("."), "preference": rdata.preference})
                        else:
                            records.append({"type": rtype, "value": str(rdata).rstrip(".") if rtype in ("NS", "PTR", "CNAME") else str(rdata)})
            except RequestBudgetExceeded:
                incomplete = True
                break
        raw_bytes = json.dumps({"target": val, "query_domain": query_domain, "records": records}).encode()
        return ProviderExecutionResult(raw_content=raw_bytes, observations=self.parse(raw_bytes, lineage),
            outcome="PARTIAL" if incomplete else "COMPLETED",
            error_message="Some DNS requests could not complete within budget" if incomplete else None)

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
                "parent_observable_value": target_val,
                "parent_observable_type": ObservableType.EMAIL,
                "parent_namespace": lineage.parent_namespace,
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
                "parent_observable_value": query_domain,
                "parent_observable_type": ObservableType.DOMAIN if "@" in target_val else lineage.parent_observable_type,
                "parent_namespace": "" if "@" in target_val else lineage.parent_namespace,
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
