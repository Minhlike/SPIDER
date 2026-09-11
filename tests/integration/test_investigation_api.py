"""Synthetic scoped investigation reads and non-destructive agent annotations."""
from uuid import uuid4
import json
import pytest
import pytest_asyncio

from spider.mcp.server import SpiderMCPServer
from spider.models.enums import ObservableType as T
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage
from spider.providers.native.public_profiles import PublicProfilesAdapter
from spider.service.service import SpiderService
from spider.storage.repositories.observation_repo import ObservationRepository
from spider.storage.schema import ProviderRunRecord, TaskRunRecord


@pytest_asyncio.fixture
async def investigation(tmp_path):
    service = SpiderService(str(tmp_path / "api.db"), str(tmp_path / "runs"))
    service.provider_manager.register_adapter(PublicProfilesAdapter())
    await service.start()
    case = await service.create_case("Synthetic")
    a = await service.add_target(case["id"], "alpha", T.USERNAME)
    b = await service.add_target(case["id"], "beta", T.USERNAME)
    observations = []
    for seed, name, run, account in ((a, "alpha", "before", "old"),
                                     (a, "alpha", "after", "new"),
                                     (b, "beta", "foreign", "foreign")):
        observations.append(Observation(
            observable=NormalizedObservable(type=T.ACCOUNT, value=f"{account}@fixture"),
            lineage=SourceLineage(case_id=case["id"], seed_id=seed["id"], run_id=run,
                task_id=run, provider_id="fixture", provider_version="1",
                upstream_family="FIXTURE", parent_observable_type=T.USERNAME, parent_observable_value=name),
            raw_data={"sentinel": "never-export-raw"}))

    async def seed_rows(session):
        seeds = [Observation(
            observable=NormalizedObservable(type=T.USERNAME, value=name),
            lineage=SourceLineage(case_id=case["id"], seed_id=target["id"],
                run_id="seed", task_id="seed", provider_id="seed_target",
                provider_version="1", upstream_family="USER_SEED"))
            for target, name in ((a, "alpha"), (b, "beta"))]
        await ObservationRepository.append_observations_batch(session, seeds)
        await service.resolution_engine.resolve_observations(session, seeds, case["id"])
        for seed, run, duration in ((a, "before", 10), (a, "after", 40), (b, "foreign", 900)):
            session.add(ProviderRunRecord(id=run, case_id=case["id"], status="COMPLETED",
                metadata_json={"expected_sources": {seed["id"]: ["fixture"]}}))
            session.add(TaskRunRecord(id=run, run_id=run, case_id=case["id"],
                execution_key_hash=run, provider_id="fixture", capability="USERNAME_DISCOVERY",
                target_observable_value="synthetic", status="COMPLETED", observations_count=1,
                metadata_json={"seed_id": seed["id"], "duration_ms": duration,
                               "request_count": 2, "provider_version": "1"}))
        session.add(ProviderRunRecord(id="browser", case_id=case["id"], status="PARTIAL",
            metadata_json={"expected_sources": {a["id"]: ["coccoc_browser"]}}))
        session.add(TaskRunRecord(id="browser-task", run_id="browser", case_id=case["id"],
            execution_key_hash="browser", provider_id="coccoc_browser", capability="BROWSER_PERSONAL_DISCOVERY",
            target_observable_value="synthetic", status="PARTIAL", observations_count=0,
            metadata_json={"seed_id": a["id"], "browser_workflow": {"owned_tabs_closed": True,
                "steps": [{"action_id": "safe-action", "step": "SEARCH_INDEX", "source": "Zalo",
                    "sanitized_url": "https://zalo.me/example?token=must-not-export", "observed_at": "2026-01-01T00:00:00Z",
                    "content_sha256": "a" * 64, "state": "UNKNOWN", "reason": "LOGIN_WALL"}]}}))
        await ObservationRepository.append_observations_batch(session, observations)
        await service.resolution_engine.resolve_observations(session, observations, case["id"])
    await service.db_writer.submit(seed_rows)
    try:
        yield service, SpiderMCPServer(service), case["id"], a["id"], b["id"], observations
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_competing_hypotheses_idempotence_and_scope(investigation):
    service, server, case, a, b, observations = investigation
    request = {"case_id": case, "target_id": a, "action_id": str(uuid4()),
               "statement": "Two accounts may be related", "supporting": [observations[0].id],
               "contradicting": [observations[1].id], "unknown": []}
    first = await server.handle_tool_call("create_hypothesis", request)
    assert first["label"] == "HYPOTHESIS" and not first["identity_verified"]
    assert first["assessment"] == "COMPETING_EVIDENCE"
    retry = await server.handle_tool_call("create_hypothesis", request)
    assert first == retry
    for changed in ({"statement": "Different"}, {"target_id": b},
                    {"supporting": [observations[2].id]},
                    {"supporting": [observations[1].id]}):
        assert "error" in await server.handle_tool_call("create_hypothesis", {**request, **changed})
    listing = await server.handle_tool_call("list_hypotheses", {"case_id": case, "target_id": a})
    assert len(listing["hypotheses"]) == 1
    other = await server.handle_tool_call("list_hypotheses", {"case_id": case, "target_id": b})
    assert not other["hypotheses"]
    assert service.is_running


@pytest.mark.asyncio
async def test_scoped_run_comparison_telemetry_and_graph(investigation):
    service, server, case, a, b, observations = investigation
    scope = {"case_id": case, "target_id": a}
    digest = await server.handle_tool_call("case_digest", scope)
    question = digest["question_state"]["questions"][0]
    assert question["id"] == "USERNAME_PUBLIC_ACCOUNTS" and question["status"] == "PARTIAL"
    assert question["reason"] == "EVIDENCE_AVAILABLE_COVERAGE_INCOMPLETE"
    assert not question["absence_verified"]
    diff = await server.handle_tool_call("compare_runs", {**scope, "before_id": "before", "after_id": "after"})
    assert diff["counts"] == {"added": 1, "not_observed": 1}
    assert not diff["absence_verified"]
    first_change = await server.handle_tool_call("compare_runs", {
        **scope, "before_id": "before", "after_id": "after", "limit": 1})
    second_change = await server.handle_tool_call("compare_runs", {
        **scope, "before_id": "before", "after_id": "after", "limit": 1,
        "snapshot": first_change["snapshot"], "after": first_change["next_cursor"]})
    assert first_change["more"] and not second_change["more"]
    assert {item["change"] for item in first_change["changes"] + second_change["changes"]} == {
        "ADDED", "NOT_OBSERVED_IN_AFTER_RUN"}
    assert "error" in await server.handle_tool_call("compare_runs", {**scope, "before_id": "before", "after_id": "foreign"})
    coverage = await server.handle_tool_call("run_coverage", {**scope, "run_id": "before"})
    assert "error" not in coverage
    assert "error" in await server.handle_tool_call("run_coverage", {**scope, "run_id": "foreign"})
    measured = await server.handle_tool_call("telemetry", scope)
    row = next(item for item in measured["providers"] if item["provider"] == "fixture")
    assert row["samples"] == 2 and row["requests"] == 4
    assert row["p50_ms"] == 10 and row["p95_ms"] == 40
    assert row["useful_evidence_count"] == 2
    assert row["useful_evidence_per_request"] == 0.5
    assert not measured["scheduler_uses_telemetry"]
    entities = await service.get_case_entities(case)
    foreign = next(e for e in entities if e["canonical_name"] == "foreign@fixture")
    own = next(e for e in entities if e["canonical_name"] == "old@fixture")
    root = next(e for e in entities if e["canonical_name"] == "alpha")
    assert "error" in await server.handle_tool_call("graph_neighbors", {**scope, "entity_id": foreign["id"]})
    graph = await server.handle_tool_call("graph_neighbors", {**scope, "entity_id": own["id"], "limit": 1})
    assert graph["evidence_ids"] == [observations[0].id]
    root_graph = await server.handle_tool_call("graph_neighbors", {**scope, "entity_id": root["id"]})
    assert root_graph["transforms"]
    assert all(item["basis"] == "REGISTERED_CAPABILITY_FOR_TYPED_ENTITY"
               and item["scope"]["target_id"] == a and item["scope"]["direct_seed"]
               and item["required_evidence_ids"] == [] for item in root_graph["transforms"])
    assert "never-export-raw" not in json.dumps(graph)
    proof = await server.handle_tool_call("explain_claim", {
        **scope, "claim_id": graph["edges"][0]["id"]})
    assert proof["rule"]["version"] == "1.0.0"
    assert proof["justification_dag"]["proof_complete"] is True
    assert "never-export-raw" not in json.dumps(proof)
    assert "error" in await server.handle_tool_call("explain_claim", {
        "case_id": case, "target_id": b, "claim_id": graph["edges"][0]["id"]})


@pytest.mark.asyncio
async def test_browser_trace_is_scoped_sanitized_and_partial_safe(investigation):
    _, server, case, a, b, _ = investigation
    trace = await server.handle_tool_call("browser_trace", {"case_id": case, "target_id": a, "run_id": "browser"})
    assert trace["owned_tabs_max"] == 3 and trace["owned_tabs_closed"]
    assert trace["resume"] == "NEW_EXPLICIT_ACTION_REQUIRED"
    assert trace["steps"][0]["sanitized_url"] == "https://zalo.me/example"
    assert "must-not-export" not in json.dumps(trace)
    assert "error" in await server.handle_tool_call("browser_trace", {"case_id": case, "target_id": b, "run_id": "browser"})


@pytest.mark.asyncio
async def test_plan_preview_is_deterministic_for_a_scoped_snapshot(investigation):
    service, server, case, a, _, _ = investigation
    target = await service.add_target(case, "gamma", T.USERNAME)
    seed = Observation(observable=NormalizedObservable(type=T.USERNAME, value="gamma"),
        lineage=SourceLineage(case_id=case, seed_id=target["id"], run_id="seed-gamma",
            task_id="seed-gamma", provider_id="seed_target", provider_version="1",
            upstream_family="USER_SEED"))

    async def materialize_seed(session):
        await ObservationRepository.append_observation(session, seed)
        await service.resolution_engine.resolve_observations(session, [seed], case)
    await service.db_writer.submit(materialize_seed)

    scope = {"case_id": case, "target_id": target["id"]}
    first = await server.handle_tool_call("plan_preview", scope)
    assert first["state"] == "READY" and first["candidates"]
    assert all(not row["dispatch"] and row["verification"]["provider_live"] == "NOT_CHECKED"
               for row in first["candidates"])
    replay = await server.handle_tool_call("plan_preview", {**scope, "snapshot": first["snapshot"]})
    assert replay == first
    assert "error" in await server.handle_tool_call("plan_preview", {
        "case_id": case, "target_id": a, "snapshot": first["snapshot"]})

    account = Observation(observable=NormalizedObservable(type=T.ACCOUNT,
        value="gamma@fixture", namespace="fixture"),
        lineage=SourceLineage(case_id=case, seed_id=target["id"], run_id="after-plan",
            task_id="after-plan", provider_id="fixture", provider_version="1",
            upstream_family="FIXTURE", parent_observable_type=T.USERNAME,
            parent_observable_value="gamma"))

    async def append_after_snapshot(session):
        await ObservationRepository.append_observation(session, account)
        await service.resolution_engine.resolve_observations(session, [account], case)
    await service.db_writer.submit(append_after_snapshot)

    assert await server.handle_tool_call("plan_preview", {**scope, "snapshot": first["snapshot"]}) == first
    fresh = await server.handle_tool_call("plan_preview", scope)
    assert fresh["state"] == "READY" and fresh["candidates"]
    assert fresh["question_state"]["questions"][0]["status"] == "PARTIAL"
    assert fresh["plan_fingerprint"] != first["plan_fingerprint"]


def test_catalogue_uses_registered_metered_contract_only(tmp_path):
    from spider.core.factory import create_spider_service
    from spider.service.investigation_api import input_catalogue
    service = create_spider_service(db_path=str(tmp_path / "catalogue.db"), artifacts_dir=str(tmp_path / "runs"))
    inputs = {item["type"]: item for item in input_catalogue(service)}
    assert inputs["IPV6_ADDRESS"]["supported"]
    for kind in ("URL", "CIDR", "ACCOUNT", "PHONE"):
        assert not inputs[kind]["supported"]
    assert all(item["live_verified"] is False for item in inputs.values())
