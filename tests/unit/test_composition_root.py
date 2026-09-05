import pytest
from spider.core.factory import create_spider_service

def test_production_mode_excludes_fake_providers():
    service = create_spider_service(mode="production")
    adapters = service.provider_manager.list_adapters()
    provider_ids = {a.provider_id() for a in adapters}
    
    assert "fake_a" not in provider_ids
    assert "fake_b" not in provider_ids
    assert "native_dns" in provider_ids
    assert "native_rdap" in provider_ids
    assert "native_ct" in provider_ids
    assert "subfinder" in provider_ids
    assert "metabigor" in provider_ids
    assert "spiderfoot" in provider_ids
    assert "maigret" in provider_ids
    assert "uncover" in provider_ids
    assert "gravatar_public" in provider_ids
    assert "whatismyip" in provider_ids

def test_test_mode_includes_fake_providers():
    service = create_spider_service(mode="test")
    adapters = service.provider_manager.list_adapters()
    provider_ids = {a.provider_id() for a in adapters}
    assert "fake_a" in provider_ids
    assert "fake_b" in provider_ids
    assert "whatismyip" in provider_ids
