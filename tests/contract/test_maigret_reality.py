import pytest
from spider.providers.maigret.adapter import MaigretAdapter
from spider.models.enums import ObservableType, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage

@pytest.mark.asyncio
async def test_maigret_real_health():
    adapter = MaigretAdapter()
    health = await adapter.health()
    assert health.state == ProviderState.READY
    assert health.provider_version == "0.6.5"
    assert health.runtime_exists is True

def test_maigret_parse_ndjson_real_output():
    adapter = MaigretAdapter()
    raw_ndjson = b'''
{"site_name": "Reddit", "url_user": "https://reddit.com/user/testuser", "status": "Found", "http_status": 200}
{"site_name": "GitHub", "url_user": "https://github.com/testuser", "status": "Found", "http_status": 200}
'''
    lineage = SourceLineage(case_id="c1", run_id="r1", task_id="t1", provider_id="maigret", provider_version="v0.6.5", parent_observable_value="testuser")
    observations = adapter.parse(raw_ndjson, lineage)
    assert len(observations) == 4 # 2 Accounts, 2 URLs
    
    accounts = [o for o in observations if o.observable.type == ObservableType.ACCOUNT]
    assert len(accounts) == 2
    assert accounts[0].observable.canonical_value == "testuser@reddit"
    assert accounts[0].confidence == 0.80 # Conservative confidence
