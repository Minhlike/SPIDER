import pytest
from spider.models.enums import ObservableType, AssertionType
from spider.models.observable import NormalizedObservable, canonicalize_observable
from spider.models.provenance import SourceLineage
from spider.models.observation import Observation
from spider.models.entity import Entity
from spider.models.assertion import Assertion

def test_observable_canonicalization():
    # Domains
    obs1 = NormalizedObservable(type=ObservableType.DOMAIN, value="  EXAMPLE.COM. ")
    assert obs1.canonical_value == "example.com"

    # IPs
    obs2 = NormalizedObservable(type=ObservableType.IP_ADDRESS, value=" 192.168.1.1 ")
    assert obs2.canonical_value == "192.168.1.1"

    # ASN
    obs3 = NormalizedObservable(type=ObservableType.ASN, value=" 15133 ")
    assert obs3.canonical_value == "AS15133"
    obs4 = NormalizedObservable(type=ObservableType.ASN, value=" as15133 ")
    assert obs4.canonical_value == "AS15133"

    # Emails
    obs5 = NormalizedObservable(type=ObservableType.EMAIL, value=" Admin@Example.com ")
    assert obs5.canonical_value == "admin@example.com"

    # Usernames
    obs6 = NormalizedObservable(type=ObservableType.USERNAME, value=" JohnDoe1998 ")
    assert obs6.canonical_value == "johndoe1998"

def test_observation_schema_and_lineage():
    lineage = SourceLineage(
        case_id="case-123",
        run_id="run-456",
        task_id="task-789",
        provider_id="fake_a",
        provider_version="1.0.0",
        upstream_source="crt.sh",
        upstream_family="CERTIFICATE_TRANSPARENCY"
    )
    obs = Observation(
        observable=NormalizedObservable(type=ObservableType.HOSTNAME, value="api.example.com"),
        lineage=lineage,
        confidence=0.9
    )
    assert obs.observable.canonical_value == "api.example.com"
    assert obs.lineage.upstream_family == "CERTIFICATE_TRANSPARENCY"
    assert obs.confidence == 0.9
