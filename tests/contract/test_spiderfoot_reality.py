import pytest
from pathlib import Path
from spider.providers.spiderfoot.adapter import SpiderFootAdapter
from spider.models.enums import ObservableType, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage

@pytest.mark.asyncio
async def test_spiderfoot_real_health():
    adapter = SpiderFootAdapter()
    health = await adapter.health()
    assert health.state == ProviderState.READY
    assert health.provider_version == "4.0.0"
    assert health.runtime_exists is True

def test_spiderfoot_parse_real_stream():
    adapter = SpiderFootAdapter()
    sample_stream = b'''
2026-09-01 [INFO] Scan initiated
{"generated": 1788272812, "type": "Internet Name", "data": "example.com", "module": "SpiderFoot UI", "source": "example.com"},
{"generated": 1788272812, "type": "Domain Name", "data": "example.com", "module": "SpiderFoot UI", "source": "example.com"},
{"generated": 1788272812, "type": "IP Address", "data": "93.184.216.34", "module": "sfp_dnsresolve", "source": "example.com"},
{"generated": 1788272812, "type": "IPv6 Address", "data": "2606:2800:220:1:248:1893:25c8:1946", "module": "sfp_dnsresolve", "source": "example.com"}[]
2026-09-01 [INFO] Scan completed
'''
    lineage = SourceLineage(case_id="c1", run_id="r1", task_id="t1", provider_id="spiderfoot", provider_version="v4.0.0")
    observations = adapter.parse(sample_stream, lineage)
    assert len(observations) == 4
    
    ip_obs = [o for o in observations if o.observable.type == ObservableType.IP_ADDRESS][0]
    assert ip_obs.observable.canonical_value == "93.184.216.34"
    assert ip_obs.lineage.upstream_source == "sf_sfp_dnsresolve"
    assert ip_obs.lineage.upstream_family == "DNS"
