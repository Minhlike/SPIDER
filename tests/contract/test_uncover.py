import pytest
from pathlib import Path
from spider.providers.uncover.adapter import UncoverAdapter
from spider.models.enums import ObservableType, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage

@pytest.mark.asyncio
async def test_uncover_health_missing_credentials_handling():
    adapter = UncoverAdapter(binary_path="tools/uncover/uncover.exe")
    health = await adapter.health()
    # When no API keys exist in env, it reports MISSING_CREDENTIAL cleanly without failing
    assert health.state in (ProviderState.MISSING_CREDENTIAL, ProviderState.READY)
    assert "v1.2.1" in health.message

def test_uncover_build_command():
    adapter = UncoverAdapter(binary_path="tools/uncover/uncover.exe")
    obs = NormalizedObservable(type=ObservableType.DOMAIN, value="target.com")
    cmd = adapter.build_command(obs)
    assert "-q" in cmd
    assert "target.com" in cmd
    assert "-oJ" in cmd
    assert "-silent" in cmd

def test_uncover_parse_frozen_fixture():
    adapter = UncoverAdapter()
    fixture_path = Path("tests/fixtures/uncover/v1.2.1_sample.jsonl")
    raw_content = fixture_path.read_bytes()

    lineage = SourceLineage(
        case_id="case-1",
        run_id="run-1",
        task_id="task-1",
        provider_id="uncover",
        provider_version="v1.2.1",
        parent_observable_value="example.com"
    )

    observations = adapter.parse(raw_content, lineage)
    assert len(observations) == 9 # 3 IPs, 3 Hosts, 3 URLs

    ips = [o for o in observations if o.observable.type == ObservableType.IP_ADDRESS]
    hosts = [o for o in observations if o.observable.type == ObservableType.HOSTNAME]
    urls = [o for o in observations if o.observable.type == ObservableType.URL]

    assert len(ips) == 3
    assert len(hosts) == 3
    assert len(urls) == 3
    assert ips[0].observable.canonical_value == "93.184.216.34"
    assert ips[0].lineage.upstream_family == "INTERNET_SCANNER"
    assert ips[0].lineage.upstream_source == "uncover_shodan"