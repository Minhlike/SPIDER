from datetime import datetime, timezone
from spider.providers.base import ProviderHealth
from spider.models.enums import ProviderState


def test_verification_defaults_and_unsupported_positive_claim_fail_closed():
    for options in ({}, {"live_verified": True, "contract_verified": True}):
        health = ProviderHealth(state=ProviderState.READY, **options)
        assert not health.live_verified and not health.contract_verified


def test_only_corresponding_versioned_evidence_promotes_stage():
    proof = {"provider_version": "1", "adapter_version": "2", "checked_at": datetime.now(timezone.utc),
             "artifact_sha256": "a" * 64}
    health = ProviderHealth(state=ProviderState.READY, provider_version="1", adapter_version="2",
        live_verified=True, contract_verified=True, verification_evidence={"contract": proof})
    assert health.contract_verified and not health.live_verified
    health = ProviderHealth(state=ProviderState.READY, provider_version="changed", adapter_version="2",
        contract_verified=True, verification_evidence={"contract": proof})
    assert not health.contract_verified
