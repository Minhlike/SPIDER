"""Actual child processes must obtain a shared parent permit before HTTP I/O."""
import asyncio
import pytest
from benchmarks.public_sites import public_sites
from spider.models.budget import BudgetLedger, ExecutionBudget
from spider.models.enums import ObservableType as T
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage
from spider.providers.maigret.adapter import MaigretAdapter
from spider.providers.permits import RequestPermits
from spider.providers.limits import OriginLimits
from spider.providers.uncover import api_access


@pytest.mark.asyncio
async def test_two_real_workers_share_atomic_cap_before_server_receives_request(tmp_path):
    ledger, budget = BudgetLedger(), ExecutionBudget(max_requests=3)
    origin_limits = OriginLimits(total=2, per_origin=1)
    received = []
    with public_sites(tmp_path, ["Present", "Wildcard"],
                      request_observer=lambda count: received.append((count, ledger.requests_count))) as sites:
        async def execute(task_id):
            return await MaigretAdapter(database_path=sites["maigret"]).execute(
                NormalizedObservable(type=T.USERNAME, value="fixture-user"),
                SourceLineage(case_id="c", run_id="r", task_id=task_id, provider_id="maigret",
                    provider_version="0.6.5", parent_observable_value="fixture-user"),
                timeout_seconds=20, request_ledger=ledger.for_task(task_id), execution_budget=budget,
                origin_limits=origin_limits)
        results = await asyncio.gather(execute("a"), execute("b"))
        assert len(sites["requests"]) == ledger.requests_count == 3
        assert all(actual <= granted <= 3 for actual, granted in received)
        assert sum(r.metadata["requests"] for r in results) == 3
        assert ledger.count_for_task("a") + ledger.count_for_task("b") == 3


@pytest.mark.asyncio
async def test_private_uncover_process_obeys_denied_parent_permit():
    # No external request: the real Go runner is denied before its HTTP transport.
    assert api_access.verified_runtime(), "Build the project-local private runner before this gate"
    ledger, budget = BudgetLedger(), ExecutionBudget(max_requests=0)
    permits = RequestPermits("uncover", ledger, budget, destination="api.shodan.io")
    result = await api_access.run_engine("shodan", {"SHODAN_API_KEY": "a" * 32},
        mode="check", on_request=permits.grant)
    assert permits.denied and permits.sequence == 1 and permits.granted == 0
    assert result["request_budget_denied"] and not result["results"]
    assert ledger.requests_count == 0


@pytest.mark.asyncio
async def test_permit_sequence_validation_and_shared_transport_budget():
    ledger, budget = BudgetLedger(), ExecutionBudget(max_requests=2)
    a = RequestPermits("worker", ledger.for_task("a"), budget)
    frame = {"kind": "request_permit", "sequence": 1,
             "destination": "fixture.test", "purpose": "lookup"}
    assert await a.grant(frame)
    ledger.for_task("native").request(budget, "native")
    assert not await a.grant({**frame, "sequence": 2, "purpose": "negative_control"})
    with pytest.raises(ValueError):
        await a.grant(frame)
    with pytest.raises(ValueError):
        await a.grant({**frame, "sequence": 3, "destination": "https://fixture.test/?key=discard"})
    assert ledger.requests_count == 2 and ledger.count_for_task("a") == 1


@pytest.mark.asyncio
async def test_cancel_worker_waiting_for_origin_permission_does_not_hang(tmp_path):
    class WaitingLimits(OriginLimits):
        async def acquire(self, origin):
            entered.set()
            return await super().acquire(origin)

    entered = asyncio.Event()
    limits = WaitingLimits(per_origin=1)
    held = await limits.acquire("127.0.0.1")
    entered.clear()
    ledger = BudgetLedger()
    with public_sites(tmp_path, ["Present"]) as sites:
        job = asyncio.create_task(MaigretAdapter(database_path=sites["maigret"]).execute(
            NormalizedObservable(type=T.USERNAME, value="fixture-user"),
            SourceLineage(case_id="c", run_id="r", task_id="waiting", provider_id="maigret",
                provider_version="0.6.5", parent_observable_value="fixture-user"),
            timeout_seconds=20, request_ledger=ledger, execution_budget=ExecutionBudget(),
            origin_limits=limits))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            job.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(job, 2)
            assert not sites["requests"] and ledger.requests_count == 0
        finally:
            held.release()
            job.cancel()
            await asyncio.gather(job, return_exceptions=True)
