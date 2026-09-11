from datetime import datetime, timezone
from types import SimpleNamespace

from spider.service.temporal import assess_source_freshness


def observation(identifier, provider="fixture", revalidate_after=None):
    metadata = {} if revalidate_after is None else {"source_freshness": {
        "provider_id": provider, "rule_id": "FIXTURE_REVALIDATION",
        "rule_version": "1.0.0", "revalidate_after": revalidate_after}}
    return SimpleNamespace(id=identifier, provider_id=provider, observable_metadata=metadata)


def test_temporal_assessment_never_turns_expiry_into_disappearance():
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    unknown = assess_source_freshness([observation("none")], now)
    assert unknown["currentness"] == "UNKNOWN"
    assert unknown["stale_status"] == "NOT_INFERRED"

    expired = assess_source_freshness([
        observation("old", revalidate_after="2026-01-01T00:00:00+00:00")], now)
    assert expired["currentness"] == "UNKNOWN"
    assert expired["stale_status"] == "REVALIDATION_DUE"
    assert expired["source_rules_applied"] == 1

    active = assess_source_freshness([
        observation("new", revalidate_after="2026-01-03T00:00:00+00:00")], now)
    assert active["currentness"] == "UNKNOWN"
    assert active["stale_status"] == "WITHIN_SOURCE_WINDOW"


def test_temporal_assessment_ignores_invalid_or_cross_provider_contracts():
    row = observation("mismatch", provider="fixture",
                      revalidate_after="2026-01-01T00:00:00+00:00")
    row.observable_metadata["source_freshness"]["provider_id"] = "other"
    result = assess_source_freshness([row], datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert result["stale_status"] == "NOT_INFERRED"
    assert result["source_rules_applied"] == 0
    assert result["invalid_source_rules_ignored"] == 1
