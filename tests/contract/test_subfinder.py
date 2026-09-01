import pytest
from pathlib import Path
from spider.providers.subfinder.adapter import SubfinderAdapter
from spider.models.enums import ObservableType, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage

@pytest.mark.asyncio
async def test_subfinder_health():
    adapter = SubfinderAdapter(binary_path="tools/subfinder/subfinder.exe")
    health = await adapter.health()
    assert health.state == ProviderState.READY
    assert "v2.16.0" in health.message

def test_subfinder_build_command():
    adapter = SubfinderAdapter(binary_path="tools/subfinder/subfinder.exe")
    obs = NormalizedObservable(type=ObservableType.DOMAIN, value="target.com")
    cmd = adapter.build_command(obs)
    assert "-d" in cmd
    assert "target.com" in cmd
    assert "-oJ" in cmd
    assert "-silent" in cmd

def test_subfinder_parse_frozen_fixture():
    adapter = SubfinderAdapter()
    fixture_path = Path("tests/fixtures/subfinder/v2.16.0_sample.jsonl")
    raw_content = fixture_path.read_bytes()

    lineage = SourceLineage(
        case_id="case-1",
        run_id="run-1",
        task_id="task-1",
        provider_id="subfinder",
        provider_version="v2.16.0",
        parent_observable_value="example.com"
    )

    observations = adapter.parse(raw_content, lineage)
    assert len(observations) == 6 # 3 hosts + 3 IPs
    
    hosts = [o for o in observations if o.observable.type == ObservableType.HOSTNAME]
    ips = [o for o in observations if o.observable.type == ObservableType.IP_ADDRESS]
    
    assert len(hosts) == 3
    assert len(ips) == 3
    assert hosts[0].observable.canonical_value == "api.example.com"
    assert hosts[0].lineage.upstream_family == "CERTIFICATE_TRANSPARENCY"
    assert hosts[1].observable.canonical_value == "admin.example.com"
    assert hosts[1].lineage.upstream_family == "SECURITY_INTELLIGENCE"
