import pytest
from spider.providers.native.dns import NativeDnsAdapter
from spider.providers.native.rdap import NativeRdapAdapter
from spider.providers.native.ct import NativeCertificateTransparencyAdapter
from spider.models.enums import ObservableType, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage

@pytest.mark.asyncio
async def test_native_dns_adapter_health():
    adapter = NativeDnsAdapter()
    health = await adapter.health()
    assert health.state == ProviderState.READY
    assert "dnspython" in health.message

@pytest.mark.asyncio
async def test_native_dns_email_decomposition_and_resolution():
    adapter = NativeDnsAdapter()
    target = NormalizedObservable(type=ObservableType.EMAIL, value="admin@example.com")
    lineage = SourceLineage(case_id="c1", run_id="r1", task_id="t1", provider_id="native_dns", provider_version="1.0.0")
    
    res = await adapter.execute(target, lineage)
    assert res.exit_code == 0
    assert len(res.observations) > 0
    
    # Must produce DOMAIN and IP observations
    types = {o.observable.type for o in res.observations}
    assert ObservableType.DOMAIN in types
    assert ObservableType.IP_ADDRESS in types or ObservableType.IPV6_ADDRESS in types

@pytest.mark.asyncio
async def test_native_rdap_health():
    adapter = NativeRdapAdapter()
    health = await adapter.health()
    assert health.state == ProviderState.READY

@pytest.mark.asyncio
async def test_native_ct_health():
    adapter = NativeCertificateTransparencyAdapter()
    health = await adapter.health()
    assert health.state == ProviderState.READY
