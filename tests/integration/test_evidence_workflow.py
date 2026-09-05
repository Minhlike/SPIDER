import json
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from spider.service.evidence_analysis import link_proofs, assess_hypothesis, temporal_events
from spider.service.drift import CanaryReport, ingest_canary
from spider.service.bundle import evidence_bundle
from spider.service.review import EvidenceReview, save_review
from spider.service.service import SpiderService
from spider.providers.fake.provider_a import FakeProviderA
from spider.models.enums import ObservableType as T
from spider.models.budget import ExecutionBudget
from spider.providers.maigret.profile_metadata import public_metadata


def obs(number, profile="https://profile.test/alice", **raw):
    return SimpleNamespace(id=str(number), observable_type="ACCOUNT", namespace="fixture",
        canonical_value="alice@fixture", created_at=datetime(2026, 1, number, tzinfo=timezone.utc),
        raw_data_json={"profile_url": profile, **raw})


def test_explicit_links_and_reciprocity_never_verify_identity():
    a = obs(1, website="https://other.test/bob")
    b = obs(2, profile="https://other.test/bob", website="https://profile.test/alice")
    proofs = link_proofs([a, b])
    assert len(proofs) == 2 and all(p["kind"] == "RECIPROCAL_LINK" and not p["identity_verified"] for p in proofs)
    assert not link_proofs([obs(3, website="javascript:alert(1)")])
    assert "secret" not in json.dumps(link_proofs([obs(4, website="https://other.test/bob?token=secret")]))


def test_mirrors_and_contradictions_do_not_become_independent_votes():
    result = assess_hypothesis([
        {"id": "1", "role": "SUPPORTING_EVIDENCE", "dependency": "INDEPENDENT_SOURCE", "origin_id": "origin"},
        {"id": "2", "role": "SUPPORTING_EVIDENCE", "dependency": "MIRRORED_SOURCE", "origin_id": "origin"},
        {"id": "3", "role": "CONTRADICTING_EVIDENCE"}, {"id": "4", "role": "UNKNOWN"}])
    assert result["dependency_clusters"] == 1 and result["review_required"]
    assert result["CONTRADICTING_EVIDENCE"] == ["3"] and not result["identity_verified"]


def test_missing_archive_is_not_disappearance_and_archived_is_not_current():
    events = temporal_events([obs(1, bio="old", archived_at="2025-01-01T00:00:00Z"),
        obs(2, archive_capture_missing=True), obs(3, bio="new")])
    assert events[0]["view"] == "ARCHIVED"
    assert events[1]["event"] == "NO_ARCHIVED_OBSERVATION"
    assert all(e["event"] != "DISAPPEARED" for e in events)


def test_link_metadata_parser_is_bounded_and_does_not_read_nested_unrelated_people():
    parsed = public_metadata('<a rel="me" href="https://fixture.test/me?token=discard#x">Me</a>'
        '<a rel="me" href="javascript:alert(1)">Bad</a>'
        '<a rel="me" href="https://user:password@fixture.test/private">Credentials</a>'
        '<script type="application/ld+json">{"@type":"Person","sameAs":["https://other.test/me"]}</script>'
        '<script type="application/ld+json">{"other":{"@type":"Person","sameAs":"https://unrelated.test"}}</script>')
    assert len(parsed["explicit_links"]) == 2
    assert parsed["explicit_links"][0]["url"] == "https://fixture.test/me"
    assert "token" not in json.dumps(parsed)


def report(bad=False):
    pairs = [("EXISTS", "CONFIRMED"), ("NOT_EXISTS", "NOT_FOUND"), ("SOFT_404", "UNKNOWN"),
             ("RATE_LIMIT", "RATE_LIMITED"), ("LOGIN_WALL", "CONFIRMED" if bad else "BLOCKED")]
    return CanaryReport(provider_version="1.0.0", adapter_version="1.0.0", dataset_sha256="a"*64,
                        results=[{"label": a, "result": b} for a, b in pairs])


@pytest.mark.asyncio
async def test_canary_quarantine_blocks_execution_and_recovers_after_two_passes(tmp_path):
    service = SpiderService(db_path=str(tmp_path / "drift.db"), artifacts_dir=str(tmp_path / "runs"))
    service.provider_manager.register_adapter(FakeProviderA())
    service.capability_registry.get_capability("SUBDOMAIN_DISCOVERY").default_providers = ["fake_a"]
    await service.start()
    try:
        result = await service.db_writer.submit(lambda s: ingest_canary(s, "fake_a", report(True)))
        assert result["state"] == "QUARANTINED"
        case = await service.create_case("Quarantined synthetic provider")
        await service.add_target(case["id"], "example.test", T.DOMAIN)
        run = await service.investigate(case["id"])
        assert run["observations_collected"] == 0 and run["status"] == "PARTIAL"
        health = await service.check_provider_health()
        assert health["fake_a"]["state"] == "QUARANTINED"
        for expected in ("QUARANTINED", "CONTRACT_PASSED"):
            recovered = await service.db_writer.submit(lambda s: ingest_canary(s, "fake_a", report()))
            assert recovered["state"] == expected
        health = await service.check_provider_health()
        assert health["fake_a"]["contract_verified"] and not health["fake_a"]["live_verified"]
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_bundle_is_reproducible_review_scoped_and_excludes_raw_payload(tmp_path):
    service = SpiderService(db_path=str(tmp_path / "bundle.db"), artifacts_dir=str(tmp_path / "runs"))
    service.provider_manager.register_adapter(FakeProviderA())
    service.capability_registry.get_capability("SUBDOMAIN_DISCOVERY").default_providers = ["fake_a"]
    await service.start()
    try:
        case = await service.create_case("Bundle fixture")
        target = await service.add_target(case["id"], "example.test", T.DOMAIN)
        await service.investigate(case["id"], ExecutionBudget(max_depth=0))
        async with service.db_manager.session_factory() as session:
            first = await evidence_bundle(session, case["id"], target["id"])
            second = await evidence_bundle(session, case["id"], target["id"])
            assert first == second and first["manifest"]["evidence_refs"]
            assert "raw_data" not in json.dumps(first)
            assert all(item["provider_id"] != "seed_target"
                       for item in first["manifest"]["observations"])
            assert all(not (item["type"] == "DOMAIN" and
                            item["canonical_value"] == "example.test")
                       for item in first["manifest"]["entities"])
            query = first["manifest"]["query_context"]
            assert query["canonical_value"] == "example.test"
            assert query["evidence"] is False and query["finding"] is False
            declared_ids = {query["entity_id"]} | {
                item["id"] for item in first["manifest"]["entities"]}
            assert all(claim["source"] in declared_ids and claim["target"] in declared_ids
                       for claim in first["manifest"]["claims"])
            claim = first["manifest"]["claims"][0]["id"]
            evidence = first["manifest"]["evidence_refs"][0]["observation_id"]
        review = EvidenceReview(target_id=target["id"], claim_id=claim, observation_id=evidence,
                               role="CONTRADICTING_EVIDENCE")
        await service.db_writer.submit(lambda s: save_review(s, case["id"], review))
        async with service.db_manager.session_factory() as session:
            bundle = await evidence_bundle(session, case["id"], target["id"])
            assert bundle["manifest"]["analysis"]["hypotheses"][0]["review_required"]
        invalid = review.model_copy(update={"target_id": "foreign"})
        with pytest.raises(ValueError):
            await service.db_writer.submit(lambda s: save_review(s, case["id"], invalid))
    finally:
        await service.stop()
