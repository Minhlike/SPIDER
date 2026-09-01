import pytest
from pathlib import Path
from spider.providers.maigret.adapter import MaigretAdapter
from spider.models.enums import ObservableType, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage

@pytest.mark.asyncio
async def test_maigret_health():
    adapter = MaigretAdapter()
    health = await adapter.health()
    assert health.state == ProviderState.READY

def test_maigret_build_command():
    adapter = MaigretAdapter()
    obs = NormalizedObservable(type=ObservableType.USERNAME, value="johndoe1998")
    cmd = adapter.build_command(obs)
    assert "-m" in cmd
    assert "maigret" in cmd
    assert "johndoe1998" in cmd

def test_maigret_parse_frozen_fixture():
    adapter = MaigretAdapter()
    fixture_path = Path("tests/fixtures/maigret/v0.6.5_sample.json")
    raw_content = fixture_path.read_bytes()

    lineage = SourceLineage(
        case_id="case-1",
        run_id="run-1",
        task_id="task-1",
        provider_id="maigret",
        provider_version="v0.6.5",
        parent_observable_value="johndoe1998"
    )

    observations = adapter.parse(raw_content, lineage)
    assert len(observations) == 4 # 2 Accounts (GitHub, Reddit) + 2 URLs

    accounts = [o for o in observations if o.observable.type == ObservableType.ACCOUNT]
    urls = [o for o in observations if o.observable.type == ObservableType.URL]

    assert len(accounts) == 2
    assert len(urls) == 2
    account_names = {a.observable.canonical_value for a in accounts}
    assert "johndoe1998@github" in account_names
    assert "johndoe1998@reddit" in account_names
