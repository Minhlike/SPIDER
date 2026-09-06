"""Offline action admission, typed lineage, owned cancellation and restart receipts."""
import asyncio
import json
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, func

from spider.capability.definitions import CapabilityDefinition
from spider.mcp.server import SpiderMCPServer
from spider.models.enums import ObservableType as T, NetworkClass
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage
from spider.providers.fake.provider_a import FakeProviderA
from spider.service.service import SpiderService
from spider.storage.repositories.observation_repo import ObservationRepository
from spider.storage.schema import InvestigationActionRecord, ProviderRunRecord, TaskRunRecord


class ControlledProvider(FakeProviderA):
    def __init__(self):
        self.calls = 0
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.release.set()
        self.tamper = None

    async def execute(self, target, lineage, **options):
        self.calls += 1
        options["request_ledger"].request(options["execution_budget"], self.provider_id())
        self.entered.set()
        await self.release.wait()
        result = await super().execute(target, lineage, **options)
        if self.tamper:
            setattr(result.observations[0].lineage, self.tamper, "foreign")
        return result


@pytest_asyncio.fixture
async def actions(tmp_path):
    service = SpiderService(str(tmp_path / "actions.db"), str(tmp_path / "runs"))
    adapter = ControlledProvider()
    service.provider_manager.register_adapter(adapter)
    service.capability_registry.register_capability(CapabilityDefinition(name="SUBDOMAIN_DISCOVERY", description="Synthetic",
        input_types=[T.DOMAIN], output_types=[T.HOSTNAME, T.IP_ADDRESS], default_providers=["fake_a"]))
    await service.start()
    case = (await service.create_case("Synthetic action test"))["id"]
    a = (await service.add_target(case, "alpha", T.USERNAME, scope_authorized=True))["id"]
    b = (await service.add_target(case, "beta", T.USERNAME))["id"]
    observations = []
    for seed, name, kind, ns in ((a, "alpha", T.DOMAIN, ""), (a, "alpha", T.DOMAIN, "other"),
                                 (a, "alpha", T.USERNAME, ""), (b, "beta", T.DOMAIN, "")):
        observations.append(Observation(observable=NormalizedObservable(
            type=kind, namespace=ns, value="fixture.example"), lineage=SourceLineage(
                case_id=case, run_id="fixture", task_id="fixture", seed_id=seed,
                provider_id="fixture", provider_version="1", parent_observable_type=T.USERNAME,
                parent_observable_value=name)))
    async def seed_rows(session):
        seeds = [Observation(observable=NormalizedObservable(type=T.USERNAME, value=name),
            lineage=SourceLineage(case_id=case, run_id="fixture", task_id="seed", seed_id=seed,
                provider_id="seed_target", provider_version="1")) for seed, name in ((a, "alpha"), (b, "beta"))]
        await ObservationRepository.append_observations_batch(session, seeds)
        await service.resolution_engine.resolve_observations(session, seeds, case)
        await ObservationRepository.append_observations_batch(session, observations)
        await service.resolution_engine.resolve_observations(session, observations, case)
    await service.db_writer.submit(seed_rows)
    entities = await service.get_case_entities(case)
    entity = next(e for e in entities if e["type"] == "DOMAIN" and e["namespace"] == "")
    request = {"case_id": case, "target_id": a, "entity_id": entity["id"], "action_id": str(uuid4()),
        "capability": "SUBDOMAIN_DISCOVERY", "provider_id": "fake_a", "observation_id": observations[0].id}
    try:
        yield service, SpiderMCPServer(service), adapter, request, b, observations
    finally:
        await service.stop()


async def settled(service):
    tasks = list(service.background_tasks)
    if tasks:
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5)


async def status(server, request):
    return await server.handle_tool_call("action_status", {
        k: request[k] for k in ("case_id", "target_id", "action_id")})


@pytest.mark.asyncio
async def test_dispatch_retry_scope_receipts_and_resolution(actions):
    service, server, adapter, request, b, observations = actions
    first = await server.handle_tool_call("run_capability", request)
    assert "error" not in first
    await settled(service)
    receipt = await status(server, request)
    retry = await server.handle_tool_call("run_capability", request)
    assert retry == receipt
    assert receipt["status"] == "COMPLETED" and receipt["observations_count"] == 6
    assert receipt["requests_count"] == 1 and adapter.calls == 1
    assert receipt["origin_observation_id"] == observations[0].id
    assert "fixture.example" not in json.dumps(receipt)
    assert not receipt["identity_verified"]
    assert (await server.handle_tool_call("run_capability", {**request, "max_requests": 2}))["error"]["code"] == "ACTION_ID_CONFLICT"
    assert "error" in await status(server, {**request, "target_id": b})
    digest = await server.handle_tool_call("case_digest", {"case_id": request["case_id"], "target_id": request["target_id"]})
    assert any(e["run_id"] == receipt["run_id"] for e in digest["evidence"])
    coverage = await server.handle_tool_call("run_coverage", {
        "case_id": request["case_id"], "target_id": request["target_id"], "run_id": receipt["run_id"]})
    assert "error" not in coverage
    assert any(e["canonical_name"] == "api.fixture.example" for e in await service.get_case_entities(request["case_id"]))


@pytest.mark.asyncio
@pytest.mark.parametrize("change,code", [
    ({"observation_id": None}, "EVIDENCE_LINK_REQUIRED"),
    ({"observation_id": "missing"}, "EVIDENCE_LINK_REQUIRED"),
    ({"entity_id": "missing"}, "ENTITY_OUTSIDE_SCOPE"),
    ({"provider_id": "missing"}, "UNSUPPORTED_CAPABILITY"),
    ({"capability": "BOGUS"}, "UNSUPPORTED_CAPABILITY"),
    ({"question": "public_profiles"}, "ENTITY_OUTSIDE_SCOPE"),
    ({"policy_profile": "missing"}, "UNKNOWN_POLICY"),
    ({"policy_profile": "local_only"}, "POLICY_DENIED"),
    ({"max_requests": 101}, "INVALID_SCOPE_OR_ARGUMENT"),
    ({"max_requests": True}, "INVALID_SCOPE_OR_ARGUMENT"),
    ({"lineage": {"seed_id": "invented"}}, "INVALID_SCOPE_OR_ARGUMENT"),
])
async def test_invalid_admission_has_no_dispatch_or_receipt(actions, change, code):
    service, server, adapter, request, _, _ = actions
    result = await server.handle_tool_call("run_capability", {**request, **change})
    assert result["error"]["code"] == code
    assert adapter.calls == 0 and not service.background_tasks
    async with service.db_manager.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(InvestigationActionRecord)) == 0


@pytest.mark.asyncio
async def test_proof_must_match_namespace_type_and_seed(actions):
    _, server, adapter, request, _, observations = actions
    for proof in observations[1:]:
        result = await server.handle_tool_call("run_capability", {**request, "observation_id": proof.id})
        assert result["error"]["code"] == "EVIDENCE_LINK_REQUIRED"
    assert adapter.calls == 0


@pytest.mark.asyncio
async def test_authorization_never_transfers_to_derived_entity(actions, monkeypatch):
    _, server, adapter, request, _, _ = actions
    monkeypatch.setattr(adapter, "network_class", lambda: NetworkClass.TARGET_DIRECT)
    result = await server.handle_tool_call("run_capability", {**request, "policy_profile": "active_authorized"})
    assert result["error"]["code"] == "POLICY_DENIED" and adapter.calls == 0


@pytest.mark.asyncio
async def test_concurrent_dispatchers_share_idempotent_admission(actions):
    service, server, adapter, request, _, _ = actions
    other = SpiderMCPServer(service)
    first, second = await asyncio.gather(server.handle_tool_call("run_capability", request),
                                        other.handle_tool_call("run_capability", request))
    assert first["run_id"] == second["run_id"]
    await settled(service)
    assert adapter.calls == 1


@pytest.mark.asyncio
async def test_unmetered_provider_is_rejected_before_dispatch(actions, monkeypatch):
    _, server, adapter, request, _, _ = actions
    monkeypatch.setattr(adapter, "request_budget_supported", False)
    assert (await server.handle_tool_call("run_capability", request))["error"]["code"] == "UNMETERED_PROVIDER"
    assert adapter.calls == 0


@pytest.mark.asyncio
async def test_bounded_queue_cancel_only_owned_run_and_retry(actions):
    service, server, adapter, request, b, _ = actions
    adapter.release.clear()
    service.actions.max_pending = 2
    first = await server.handle_tool_call("run_capability", request)
    await asyncio.wait_for(adapter.entered.wait(), 3)
    second_args = {**request, "action_id": str(uuid4())}
    second = await server.handle_tool_call("run_capability", second_args)
    assert second["status"] == "QUEUED" and adapter.calls == 1
    third = await server.handle_tool_call("run_capability", {**request, "action_id": str(uuid4())})
    assert third["error"]["code"] == "ACTION_QUEUE_FULL"
    cancel = {"case_id": request["case_id"], "target_id": request["target_id"],
              "run_id": second["run_id"], "action_id": str(uuid4())}
    assert "error" in await server.handle_tool_call("cancel_run", {**cancel, "target_id": b})
    cancelled = await server.handle_tool_call("cancel_run", cancel)
    assert cancelled["status"] == "CANCELLED" and adapter.calls == 1
    assert await server.handle_tool_call("cancel_run", cancel) == cancelled
    first_cancel = await server.handle_tool_call("cancel_run", {
        **cancel, "action_id": str(uuid4()), "run_id": first["run_id"]})
    assert first_cancel["status"] == "CANCELLED" and first_cancel["requests_count"] == 1
    assert (await server.handle_tool_call("run_capability", request))["status"] == "CANCELLED"
    assert adapter.calls == 1


@pytest.mark.asyncio
async def test_shutdown_drain_and_unknown_restart_never_redispatch(actions):
    service, server, adapter, request, _, _ = actions
    adapter.release.clear()
    first = await server.handle_tool_call("run_capability", request)
    await asyncio.wait_for(adapter.entered.wait(), 3)
    await service.stop()
    await service.start()
    assert (await status(server, request))["status"] == "CANCELLED"
    # Simulate a persisted RUNNING receipt after a process crash, no attached owner.
    async def orphan(session):
        row = await session.get(ProviderRunRecord, first["run_id"])
        row.status = "RUNNING"
    await service.db_writer.submit(orphan)
    retried = await server.handle_tool_call("run_capability", request)
    assert retried["status"] == "UNKNOWN_AFTER_RESTART" and not retried["automatic_replay"]
    assert adapter.calls == 1 and not service.background_tasks


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["case_id", "run_id", "task_id", "provider_id", "seed_id"])
async def test_ingest_rejects_foreign_lineage(actions, field):
    service, server, adapter, request, _, _ = actions
    adapter.tamper = field
    await server.handle_tool_call("run_capability", request)
    await settled(service)
    result = await status(server, request)
    assert result["status"] == "FAILED" and result["observations_count"] == 0


@pytest.mark.asyncio
async def test_cancellation_retains_atomic_evidence_and_graph(actions, monkeypatch):
    service, server, _, request, _, _ = actions
    committed = asyncio.Event()
    original = service.ingest_queue.ingest_batch
    async def ingest(*args, **kwargs):
        await original(*args, **kwargs)
        committed.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(service.ingest_queue, "ingest_batch", ingest)
    receipt = await server.handle_tool_call("run_capability", request)
    await asyncio.wait_for(committed.wait(), 3)
    result = await server.handle_tool_call("cancel_run", {
        "case_id": request["case_id"], "target_id": request["target_id"],
        "run_id": receipt["run_id"], "action_id": str(uuid4())})
    assert result["status"] == "CANCELLED" and result["observations_count"] == 6
    assert any(e["canonical_name"] == "api.fixture.example" for e in await service.get_case_entities(request["case_id"]))
    async with service.db_manager.session_factory() as session:
        tasks = list((await session.scalars(select(TaskRunRecord).where(TaskRunRecord.run_id == receipt["run_id"]))).all())
        assert tasks[0].status == "CANCELLED"


@pytest.mark.asyncio
async def test_mutation_requires_session_without_creating_db(tmp_path):
    service = SpiderService(str(tmp_path / "absent.db"), str(tmp_path / "runs"))
    result = await SpiderMCPServer(service).handle_tool_call("run_capability", {})
    assert result["error"]["code"] == "SESSION_REQUIRED"
    assert not (tmp_path / "absent.db").exists()


@pytest.mark.asyncio
async def test_navigation_annotation_retry_does_not_undo_newer_review(actions):
    service, server, _, request, b, observations = actions
    cases = await server.handle_tool_call("list_cases", {"limit": 1})
    assert cases["items"][0]["id"] == request["case_id"]
    targets = await server.handle_tool_call("list_targets", {"case_id": request["case_id"], "limit": 1})
    tail = await server.handle_tool_call("list_targets", {
        "case_id": request["case_id"], "limit": 1, "after": targets["next_cursor"]})
    assert {targets["items"][0]["id"], tail["items"][0]["id"]} == {request["target_id"], b}
    assert not tail["more"]
    assert "error" in await server.handle_tool_call("list_targets", {"case_id": "foreign"})
    detail = await server.handle_tool_call("get_evidence", {"case_id": request["case_id"],
        "target_id": request["target_id"], "observation_id": observations[0].id})
    assert detail["entity_id"] == request["entity_id"]
    graph = await server.handle_tool_call("graph_neighbors", {"case_id": request["case_id"],
        "target_id": request["target_id"], "entity_id": detail["entity_id"]})
    annotation = {"case_id": request["case_id"], "target_id": request["target_id"],
        "action_id": str(uuid4()), "claim_id": graph["edges"][0]["id"],
        "observation_id": observations[0].id, "role": "SUPPORTING_EVIDENCE"}
    first = await server.handle_tool_call("annotate_evidence", annotation)
    assert first["status"] == "ANNOTATED" and not first["identity_verified"]
    second = await server.handle_tool_call("annotate_evidence", {
        **annotation, "action_id": str(uuid4()), "role": "CONTRADICTING_EVIDENCE"})
    assert second["status"] == "ANNOTATED"
    assert await server.handle_tool_call("annotate_evidence", annotation) == first
    from spider.storage.schema import EvidenceReviewRecord
    async with service.db_manager.session_factory() as session:
        review = await session.scalar(select(EvidenceReviewRecord))
        assert review.role == "CONTRADICTING_EVIDENCE"
    assert "error" in await server.handle_tool_call("annotate_evidence", {**annotation, "role": "UNKNOWN"})
    assert "error" in await server.handle_tool_call("annotate_evidence", {
        **annotation, "action_id": str(uuid4()), "observation_id": observations[-1].id})
