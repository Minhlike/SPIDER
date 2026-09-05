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
from spider.service.service import SpiderService
from spider.storage.repositories.observation_repo import ObservationRepository
from spider.storage.schema import ProviderRunRecord, TaskRunRecord


@pytest_asyncio.fixture
async def investigation(tmp_path):
    service = SpiderService(str(tmp_path / "api.db"), str(tmp_path / "runs"))
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
                parent_observable_type=T.USERNAME, parent_observable_value=name),
            raw_data={"sentinel": "never-export-raw"}))

    async def seed_rows(session):
        for seed, run, duration in ((a, "before", 10), (a, "after", 40), (b, "foreign", 900)):
            session.add(ProviderRunRecord(id=run, case_id=case["id"], status="COMPLETED",
                metadata_json={"expected_sources": {seed["id"]: ["fixture"]}}))
            session.add(TaskRunRecord(id=run, run_id=run, case_id=case["id"],
                execution_key_hash=run, provider_id="fixture", capability="USERNAME_DISCOVERY",
                target_observable_value="synthetic", status="COMPLETED", observations_count=1,
                metadata_json={"seed_id": seed["id"], "duration_ms": duration,
                               "request_count": 2, "provider_version": "1"}))
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
    diff = await server.handle_tool_call("compare_runs", {**scope, "before_id": "before", "after_id": "after"})
    assert diff["counts"] == {"added": 1, "not_observed": 1}
    assert not diff["absence_verified"]
    assert "error" in await server.handle_tool_call("compare_runs", {**scope, "before_id": "before", "after_id": "foreign"})
    coverage = await server.handle_tool_call("run_coverage", {**scope, "run_id": "before"})
    assert "error" not in coverage
    assert "error" in await server.handle_tool_call("run_coverage", {**scope, "run_id": "foreign"})
    measured = await server.handle_tool_call("telemetry", scope)
    row = measured["providers"][0]
    assert row["samples"] == 2 and row["requests"] == 4
    assert row["p50_ms"] == 10 and row["p95_ms"] == 40
    assert row["useful_evidence_per_request"] is None
    assert not measured["scheduler_uses_telemetry"]
    entities = await service.get_case_entities(case)
    foreign = next(e for e in entities if e["canonical_name"] == "foreign@fixture")
    own = next(e for e in entities if e["canonical_name"] == "old@fixture")
    assert "error" in await server.handle_tool_call("graph_neighbors", {**scope, "entity_id": foreign["id"]})
    graph = await server.handle_tool_call("graph_neighbors", {**scope, "entity_id": own["id"], "limit": 1})
    assert graph["evidence_ids"] == [observations[0].id]
    assert "never-export-raw" not in json.dumps(graph)


def test_catalogue_uses_registered_metered_contract_only(tmp_path):
    from spider.core.factory import create_spider_service
    from spider.service.investigation_api import input_catalogue
    service = create_spider_service(db_path=str(tmp_path / "catalogue.db"), artifacts_dir=str(tmp_path / "runs"))
    inputs = {item["type"]: item for item in input_catalogue(service)}
    assert inputs["IPV6_ADDRESS"]["supported"]
    for kind in ("URL", "CIDR", "ACCOUNT", "PHONE"):
        assert not inputs[kind]["supported"]
    assert all(item["live_verified"] is False for item in inputs.values())
