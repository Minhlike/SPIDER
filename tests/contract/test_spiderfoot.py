import pytest
from pathlib import Path
from spider.providers.spiderfoot.adapter import SpiderFootAdapter
from spider.models.enums import ObservableType, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage

@pytest.mark.asyncio
async def test_spiderfoot_health():
    adapter = SpiderFootAdapter()
    health = await adapter.health()
    assert health.state == ProviderState.READY

def test_spiderfoot_build_command():
    adapter = SpiderFootAdapter()
    obs = NormalizedObservable(type=ObservableType.DOMAIN, value="target.com")
    cmd = adapter.build_command(obs)
    assert "-s" in cmd
    assert "target.com" in cmd
    assert "-o" in cmd
    assert "json" in cmd

def test_spiderfoot_parse_frozen_fixture():
    adapter = SpiderFootAdapter()
    fixture_path = Path("tests/fixtures/spiderfoot/v4.0_sample.json")
    raw_content = fixture_path.read_bytes()

    lineage = SourceLineage(
        case_id="case-1",
        run_id="run-1",
        task_id="task-1",
        provider_id="spiderfoot",
        provider_version="v4.0",
        parent_observable_value="example.com"
    )

    observations = adapter.parse(raw_content, lineage)
    assert len(observations) == 6

    types = {o.observable.type for o in observations}
    assert ObservableType.HOSTNAME in types
    assert ObservableType.IP_ADDRESS in types
    assert ObservableType.EMAIL in types
    assert ObservableType.PHONE in types
    assert ObservableType.ASN in types
    assert ObservableType.USERNAME in types

    email_obs = next(o for o in observations if o.observable.type == ObservableType.EMAIL)
    assert email_obs.observable.canonical_value == "security@example.com"
    assert email_obs.lineage.upstream_family == "EMAIL_INTELLIGENCE"
    assert email_obs.confidence == 0.9
