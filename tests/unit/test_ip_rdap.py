import json

from spider.models.enums import ObservableType
from spider.models.provenance import SourceLineage
from spider.providers.native.rdap import NativeRdapAdapter


def lineage():
    return SourceLineage(case_id="case", run_id="run", task_id="task",
                         provider_id="native_rdap", provider_version="1",
                         parent_observable_value="8.8.8.8",
                         parent_observable_type=ObservableType.IP_ADDRESS)


def test_global_rdap_extracts_registry_range_events_and_operational_contacts():
    payload = {"rdap": {
        "objectClassName": "ip network", "name": "GOGL", "handle": "NET-8-8-8-0-2",
        "startAddress": "8.8.8.0", "endAddress": "8.8.8.255", "country": "US",
        "port43": "whois.arin.net", "status": ["active"],
        "cidr0_cidrs": [{"v4prefix": "8.8.8.0", "length": 24}],
        "events": [{"eventAction": "last changed", "eventDate": "2025-01-01T00:00:00Z"}],
        "entities": [{"roles": ["abuse"], "vcardArray": ["vcard", [
            ["fn", {}, "text", "Google LLC"],
            ["email", {"type": "work"}, "text", "abuse@example.invalid"],
        ]]}],
    }, "bgpview": {"data": {"prefixes": [{
        "prefix": "8.8.8.0/24", "asn": {"asn": 15169, "name": "GOOGLE", "country_code": "US"}
    }]}}}
    observations = NativeRdapAdapter().parse(json.dumps(payload).encode(), lineage())
    assert any(o.observable.type == ObservableType.ASN and o.observable.canonical_value == "AS15169"
               for o in observations)
    rdap = next(o.raw_data for o in observations if o.raw_data.get("record_kind") == "rdap_network")
    assert rdap["rir"] == "ARIN" and rdap["cidrs"] == ["8.8.8.0/24"]
    assert rdap["contacts"][0]["roles"] == ["abuse"]
    assert rdap["events"][0]["action"] == "last changed"


def test_ipv6_is_supported_and_range_can_be_summarized():
    adapter = NativeRdapAdapter()
    assert ObservableType.IPV6_ADDRESS in adapter.accepts()
    payload = {"rdap": {"objectClassName": "ip network", "name": "V6-NET",
        "startAddress": "2001:4860::", "endAddress": "2001:4860:ffff:ffff:ffff:ffff:ffff:ffff"}}
    observations = adapter.parse(json.dumps(payload).encode(), lineage())
    assert any(o.observable.type == ObservableType.CIDR and
               o.observable.canonical_value == "2001:4860::/32" for o in observations)
