import pytest
from pathlib import Path
from spider.providers.metabigor.adapter import MetabigorAdapter
from spider.models.enums import ObservableType, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage

@pytest.mark.asyncio
async def test_metabigor_health():
    adapter = MetabigorAdapter(binary_path="tools/metabigor/metabigor.exe")
    health = await adapter.health()
    assert health.state == ProviderState.READY
    assert "v2.2.0" in health.message

def test_metabigor_build_command():
    adapter = MetabigorAdapter(binary_path="tools/metabigor/metabigor.exe")
    obs = NormalizedObservable(type=ObservableType.ASN, value="AS15133")
    cmd = adapter.build_command(obs)
    assert "net" in cmd
    assert "AS15133" in cmd
    assert "-f" in cmd
    assert "json" in cmd

def test_metabigor_parse_frozen_fixture():
    adapter = MetabigorAdapter()
    fixture_path = Path("tests/fixtures/metabigor/v2.2.0_sample.json")
    raw_content = fixture_path.read_bytes()

    lineage = SourceLineage(
        case_id="case-1",
        run_id="run-1",
        task_id="task-1",
        provider_id="metabigor",
        provider_version="v2.2.0",
        parent_observable_value="93.184.216.34"
    )

    observations = adapter.parse(raw_content, lineage)
    assert len(observations) == 6 # 2 ASNs, 2 Orgs, 2 CIDRs

    asns = [o for o in observations if o.observable.type == ObservableType.ASN]
    orgs = [o for o in observations if o.observable.type == ObservableType.ORGANIZATION]
    cidrs = [o for o in observations if o.observable.type == ObservableType.CIDR]

    assert len(asns) == 2
    assert len(orgs) == 2
    assert len(cidrs) == 2
    assert asns[0].observable.canonical_value == "AS15133"
    assert cidrs[0].observable.canonical_value == "93.184.216.0/24"
    assert orgs[0].observable.canonical_value == "EdgeCast Networks, Inc."
