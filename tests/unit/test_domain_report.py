from types import SimpleNamespace
import json

from spider.service.insights import domain_evidence_profile
from spider.providers.native.dns import NativeDnsAdapter
from spider.models.provenance import SourceLineage
from spider.models.enums import ObservableType


def test_domain_profile_only_reports_observed_dns_certificate_and_scanner_fields():
    observations = [
        SimpleNamespace(provider_id="native_dns", raw_data_json={"type": "A", "value": "192.0.2.4"}),
        SimpleNamespace(provider_id="native_dns", raw_data_json={"type": "TXT", "value": "v=spf1 -all"}),
        SimpleNamespace(provider_id="native_dns", raw_data_json={"type": "DMARC", "value": "v=DMARC1; p=reject"}),
        SimpleNamespace(provider_id="native_dns", raw_data_json={"type": "CAA", "value": '0 issue "ca.example"'}),
        SimpleNamespace(provider_id="native_ct", raw_data_json={"issuer_name": "Test CA", "not_after": "2030-01-01"}),
        SimpleNamespace(provider_id="uncover", raw_data_json={"engine": "shodan", "host": "www.example.test", "port": 443, "server": "nginx"}),
        SimpleNamespace(provider_id="native_web", raw_data_json={"record_kind": "authorized_web_metadata",
            "url": "https://example.test/", "http_status": 200, "title": "Fixture", "server": "nginx",
            "has_hsts": True, "has_csp": False}),
        SimpleNamespace(provider_id="uncover", raw_data_json={"owner": "must-not-be-present"}),
    ]

    profile = domain_evidence_profile(observations)

    assert profile["dns_records"]["A"] == ["192.0.2.4"]
    assert profile["dns_security"] == {
        "spf": ["v=spf1 -all"], "dmarc": ["v=DMARC1; p=reject"], "caa": ['0 issue "ca.example"']}
    assert profile["certificates"] == [{"issuer_name": "Test CA", "not_after": "2030-01-01"}]
    assert profile["public_services"] == [{"engine": "shodan", "host": "www.example.test", "port": 443}]
    assert profile["technology_signals"] == ["nginx"]
    assert profile["web_metadata"] == [{"url": "https://example.test/", "http_status": 200,
                                         "title": "Fixture", "has_hsts": True, "has_csp": False}]


def test_dns_parser_retains_domain_level_security_records_as_evidence():
    raw = json.dumps({"target": "example.test", "query_domain": "example.test", "records": [
        {"type": "TXT", "value": "v=spf1 -all"},
        {"type": "DMARC", "value": "v=DMARC1; p=reject"},
        {"type": "CAA", "value": '0 issue "ca.example"'},
    ]}).encode()
    observations = NativeDnsAdapter().parse(raw, SourceLineage(
        case_id="case", run_id="run", task_id="task", provider_id="native_dns", provider_version="1"))

    assert {item.observable.type for item in observations} == {ObservableType.DOMAIN}
    profile = domain_evidence_profile([
        SimpleNamespace(provider_id="native_dns", raw_data_json=item.raw_data) for item in observations])
    assert profile["dns_security"]["spf"] == ["v=spf1 -all"]
    assert profile["dns_security"]["dmarc"] == ["v=DMARC1; p=reject"]
    assert profile["dns_security"]["caa"] == ['0 issue "ca.example"']
