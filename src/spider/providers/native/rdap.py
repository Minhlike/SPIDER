"""Global RDAP bootstrap plus routing-prefix enrichment."""
from __future__ import annotations

import ipaddress
import json
from typing import Any, List
from urllib.parse import quote

import httpx

from spider.models.budget import RequestBudgetExceeded
from spider.models.enums import NetworkClass, ObservableType, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage
from spider.providers.base import BaseProviderAdapter, ProviderExecutionResult, ProviderHealth
from spider.providers.transport import provider_client


def _vcard_fields(entity: dict) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    card = entity.get("vcardArray")
    if not isinstance(card, list) or len(card) != 2 or not isinstance(card[1], list):
        return result
    for row in card[1]:
        if not isinstance(row, list) or len(row) < 4 or not isinstance(row[0], str):
            continue
        values = row[3] if isinstance(row[3], list) else [row[3]]
        clean = [str(item).strip() for item in values if str(item).strip()]
        if clean:
            result.setdefault(row[0].casefold(), []).extend(clean)
    return result


def _rir_name(data: dict) -> str | None:
    haystacks = [str(data.get(name, "")).casefold() for name in ("port43", "handle", "name")]
    haystacks += [str(link.get("href", "")).casefold() for link in data.get("links", [])
                  if isinstance(link, dict)]
    for name in ("arin", "apnic", "ripe", "lacnic", "afrinic"):
        if any(name in value for value in haystacks):
            return name.upper()
    return None


def _cidrs(data: dict) -> list[str]:
    result = []
    for item in data.get("cidr0_cidrs", []):
        if not isinstance(item, dict):
            continue
        prefix = item.get("v4prefix") or item.get("v6prefix")
        length = item.get("length")
        if prefix is not None and isinstance(length, int):
            try:
                result.append(str(ipaddress.ip_network(f"{prefix}/{length}", strict=False)))
            except ValueError:
                pass
    if result:
        return list(dict.fromkeys(result))
    try:
        start = ipaddress.ip_address(data["startAddress"])
        end = ipaddress.ip_address(data["endAddress"])
        if start.version == end.version:
            return [str(item) for item in ipaddress.summarize_address_range(start, end)]
    except (KeyError, ValueError, TypeError):
        pass
    return []


def _rdap_summary(data: dict) -> dict:
    contacts, organizations = [], []
    for entity in data.get("entities", []):
        if not isinstance(entity, dict):
            continue
        fields = _vcard_fields(entity)
        roles = [str(role) for role in entity.get("roles", []) if isinstance(role, str)]
        names = fields.get("fn", []) + fields.get("org", [])
        organizations.extend(names)
        emails = fields.get("email", [])
        if names or emails:
            contacts.append({"roles": roles, "names": names, "emails": emails})
    events = [{"action": event["eventAction"], "date": event["eventDate"]}
              for event in data.get("events", []) if isinstance(event, dict)
              and event.get("eventAction") and event.get("eventDate")]
    return {
        "record_kind": "rdap_network",
        "network_name": data.get("name"),
        "handle": data.get("handle"),
        "country": data.get("country"),
        "start_address": data.get("startAddress"),
        "end_address": data.get("endAddress"),
        "cidrs": _cidrs(data),
        "status": [str(item) for item in data.get("status", []) if isinstance(item, str)],
        "rir": _rir_name(data),
        "events": events,
        "contacts": contacts,
        "organizations": list(dict.fromkeys(organizations)),
    }


class NativeRdapAdapter(BaseProviderAdapter):
    request_budget_supported = True

    def provider_id(self) -> str:
        return "native_rdap"

    def version(self) -> str:
        return "1.0.0"

    def adapter_version(self) -> str:
        return "1.1.0"

    def capabilities(self) -> List[str]:
        return ["REGISTRY_LOOKUP", "INFRASTRUCTURE_DISCOVERY"]

    def network_class(self) -> NetworkClass:
        return NetworkClass.THIRD_PARTY_ONLY

    def accepts(self) -> List[ObservableType]:
        return [ObservableType.IP_ADDRESS, ObservableType.IPV6_ADDRESS,
                ObservableType.ASN, ObservableType.DOMAIN]

    def produces(self) -> List[ObservableType]:
        return [ObservableType.ASN, ObservableType.CIDR, ObservableType.ORGANIZATION]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(state=ProviderState.READY,
                              message="Global RDAP bootstrap client available")

    def build_command(self, target: NormalizedObservable) -> List[str]:
        return ["internal", "rdap_query", target.canonical_value]

    async def execute(self, target: NormalizedObservable, lineage: SourceLineage,
                      **kwargs) -> ProviderExecutionResult:
        value = target.canonical_value
        if target.type in (ObservableType.IP_ADDRESS, ObservableType.IPV6_ADDRESS):
            try:
                address = ipaddress.ip_address(value)
            except ValueError:
                return ProviderExecutionResult(raw_content=b"", observations=[], exit_code=1,
                                               error_message="Invalid IP address")
            if not address.is_global:
                return ProviderExecutionResult(raw_content=b"{}", observations=[], outcome="COMPLETED",
                    metadata={"collection_state": "LOCAL_ONLY_ADDRESS", "request_count": 0})
            rdap_url = f"https://rdap.org/ip/{quote(value, safe=':')}"
        elif target.type == ObservableType.ASN:
            rdap_url = f"https://rdap.org/autnum/{value.removeprefix('AS')}"
        else:
            rdap_url = f"https://rdap.org/domain/{quote(value, safe='')}"

        envelope: dict[str, Any] = {}
        errors = []
        try:
            async with provider_client(self.provider_id(), kwargs, timeout=7,
                                       follow_redirects=True,
                                       transport=kwargs.get("transport")) as client:
                try:
                    response = await client.get(rdap_url, extensions={
                        "spider_purpose": "authoritative_registry_lookup",
                        "spider_identifier": target,
                    })
                    rdap_data = response.json() if response.status_code == 200 else None
                    if isinstance(rdap_data, dict):
                        envelope["rdap"] = rdap_data
                    else:
                        errors.append("RDAP_UNAVAILABLE")
                except (httpx.HTTPError, ValueError, json.JSONDecodeError):
                    errors.append("RDAP_UNAVAILABLE")

                if target.type in (ObservableType.IP_ADDRESS, ObservableType.IPV6_ADDRESS):
                    try:
                        response = await client.get(
                            f"https://api.bgpview.io/ip/{quote(value, safe=':')}",
                            extensions={"spider_purpose": "routing_prefix_lookup",
                                        "spider_identifier": target},
                        )
                        bgp_data = response.json() if response.status_code == 200 else None
                        if isinstance(bgp_data, dict):
                            envelope["bgpview"] = bgp_data
                        else:
                            errors.append("BGP_UNAVAILABLE")
                    except RequestBudgetExceeded:
                        errors.append("REQUEST_LIMIT")
                    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
                        errors.append("BGP_UNAVAILABLE")
        except RequestBudgetExceeded:
            raise
        except httpx.HTTPError:
            errors.append("NETWORK_ERROR")

        raw = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        observations = self.parse(raw, lineage)
        if not envelope:
            return ProviderExecutionResult(raw_content=raw, observations=[], exit_code=1,
                outcome="PARTIAL", error_message="Registry and routing responses unavailable",
                metadata={"collection_state": errors})
        return ProviderExecutionResult(raw_content=raw, observations=observations,
            exit_code=0, outcome="PARTIAL" if errors else "COMPLETED",
            error_message="Some registry enrichment was unavailable" if errors else None,
            metadata={"collection_state": errors or ["COMPLETE"]},
            raw_items_count=len(envelope), accepted_count=len(observations))

    def parse(self, raw_content: bytes, lineage: SourceLineage) -> List[Observation]:
        try:
            envelope = json.loads(raw_content.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return []
        if not isinstance(envelope, dict) or "error" in envelope:
            return []
        rdap = envelope.get("rdap") if isinstance(envelope.get("rdap"), dict) else None
        bgp = envelope.get("bgpview") if isinstance(envelope.get("bgpview"), dict) else None
        if rdap is None and bgp is None:
            if isinstance(envelope.get("data"), dict):
                bgp = envelope
            elif any(key in envelope for key in ("rdapConformance", "startAddress", "objectClassName")):
                rdap = envelope

        results: List[Observation] = []
        if rdap:
            summary = _rdap_summary(rdap)
            item_lineage = lineage.model_copy(update={
                "upstream_source": "global_rdap", "upstream_family": "ROUTING_REGISTRY"})
            for cidr in summary["cidrs"]:
                results.append(Observation(observable=self.normalize(
                    {"type": ObservableType.CIDR, "value": cidr}), lineage=item_lineage,
                    confidence=0.97, raw_data=summary))
            organization = next(iter(summary["organizations"]), None) or summary["network_name"]
            if organization:
                results.append(Observation(observable=self.normalize(
                    {"type": ObservableType.ORGANIZATION, "value": organization}),
                    lineage=item_lineage, confidence=0.92, raw_data=summary))

        data = bgp.get("data", {}) if bgp else {}
        if isinstance(data, dict):
            for prefix in data.get("prefixes", []):
                if not isinstance(prefix, dict):
                    continue
                asn_info = prefix.get("asn", {}) if isinstance(prefix.get("asn"), dict) else {}
                asn_num = asn_info.get("asn")
                asn_value = f"AS{asn_num}" if asn_num else None
                summary = {"record_kind": "bgp_prefix", "prefix": prefix.get("prefix"),
                           "asn": asn_value, "organization": asn_info.get("name"),
                           "country": asn_info.get("country_code")}
                item_lineage = lineage.model_copy(update={
                    "upstream_source": "bgpview", "upstream_family": "BGP_ROUTING"})
                for kind, item, confidence in (
                    (ObservableType.ASN, asn_value, 0.94),
                    (ObservableType.CIDR, prefix.get("prefix"), 0.94),
                    (ObservableType.ORGANIZATION, asn_info.get("name"), 0.90),
                ):
                    if item:
                        results.append(Observation(observable=self.normalize(
                            {"type": kind, "value": item}), lineage=item_lineage,
                            confidence=confidence, raw_data=summary))
        return results

    def normalize(self, raw_item: Any) -> NormalizedObservable:
        return NormalizedObservable(type=raw_item["type"], value=raw_item["value"])
