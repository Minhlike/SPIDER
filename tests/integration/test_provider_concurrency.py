import asyncio
import pytest
from benchmarks.provider_concurrency import trial
from spider.providers.limits import OriginLimits


@pytest.mark.asyncio
async def test_widths_preserve_evidence_and_graph_with_reverse_completion(tmp_path):
    rows = []
    for width in (1, 2, 4):
        folder = tmp_path / str(width)
        folder.mkdir()
        rows.append(await trial(folder, width, delays=(.10, .07, .04, .01)))
    assert [r["peak_providers"] for r in rows] == [1, 2, 4]
    assert all(r["requests"] == 4 and r["status"] == "COMPLETED" for r in rows)
    assert all(r["entities"] == rows[0]["entities"] and r["graph"] == rows[0]["graph"] for r in rows)


@pytest.mark.asyncio
async def test_entity_cap_admission_uses_schedule_not_completion_order(tmp_path):
    rows = []
    for width in (1, 4):
        folder = tmp_path / str(width)
        folder.mkdir()
        rows.append(await trial(folder, width, entity_cap=3, delays=(.10, .07, .04, .01)))
    assert rows[0]["entities"] == rows[1]["entities"]
    assert len(rows[0]["entities"]) == 3
    assert rows[0]["status"] == rows[1]["status"] == "PARTIAL"


@pytest.mark.asyncio
async def test_concurrent_provider_requests_share_hard_cap(tmp_path):
    row = await trial(tmp_path, 4, request_cap=2)
    assert row["requests"] == 2 and row["observations"] == 2
    assert row["status"] == "PARTIAL"


@pytest.mark.asyncio
async def test_origin_limits_bound_requests_and_release_cancelled_waiter():
    limits = OriginLimits(total=2, per_origin=1, max_origins=2)
    a, b = await limits.acquire("a"), await limits.acquire("b")
    pending = asyncio.create_task(limits.acquire("c"))
    await asyncio.sleep(0)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    a.release()
    c = await asyncio.wait_for(limits.acquire("c"), 1)
    blocked = asyncio.create_task(limits.acquire("d"))
    await asyncio.sleep(0)
    assert not blocked.done()  # Excess origins share one bounded fallback.
    c.release()
    d = await asyncio.wait_for(blocked, 1)
    d.release()
    b.release()
    assert len(limits.origins) == 2


@pytest.mark.asyncio
async def test_429_backoff_is_per_origin_bounded_and_does_not_add_requests():
    now, sleeps = [0], []
    async def sleep(delay):
        sleeps.append(delay)
        now[0] += delay
    limits = OriginLimits(clock=lambda: now[0], sleep=sleep)
    (await limits.acquire("a")).release()
    limits.feedback("a", 429, "9999999999999999")
    (await limits.acquire("b")).release()
    assert not sleeps
    (await limits.acquire("a")).release()
    assert sleeps == [30]


@pytest.mark.asyncio
async def test_cancel_parallel_run_drains_tasks_and_persists_cancelled_state(tmp_path):
    from sqlalchemy import select
    from benchmarks.provider_concurrency import Tracker, DelayedFixture
    from spider.models.budget import ExecutionBudget
    from spider.models.enums import ObservableType as T
    from spider.service.service import SpiderService
    from spider.storage.schema import ProviderRunRecord, TaskRunRecord
    service = SpiderService(str(tmp_path / "cancel.db"), str(tmp_path / "runs"))
    tracker = Tracker()
    for i in range(4):
        service.provider_manager.register_adapter(DelayedFixture(i, tracker, delay=5))
    service.capability_registry.get_capability("SUBDOMAIN_DISCOVERY").default_providers = list(service.provider_manager.adapters)
    await service.start()
    try:
        case = (await service.create_case("Synthetic cancellation"))["id"]
        await service.add_target(case, "fixture.test", T.DOMAIN)
        job = asyncio.create_task(service.investigate(case, ExecutionBudget(max_parallel_tasks=4)))
        async def entered():
            while tracker.active < 4:
                await asyncio.sleep(.01)
        await asyncio.wait_for(entered(), 3)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        assert tracker.active == 0
        async with service.db_manager.session_factory() as session:
            run = await session.scalar(select(ProviderRunRecord))
            tasks = list((await session.scalars(select(TaskRunRecord))).all())
        assert run.status == "CANCELLED" and run.tasks_count == 4
        assert len(tasks) == 4 and all(t.status == "CANCELLED" for t in tasks)
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_provider_and_global_limits_are_shared_across_runs(tmp_path):
    from collections import defaultdict
    from benchmarks.provider_concurrency import Tracker, DelayedFixture
    from spider.models.budget import ExecutionBudget
    from spider.models.enums import ObservableType as T
    from spider.service.service import SpiderService
    active, peaks = defaultdict(int), defaultdict(int)

    class CountedFixture(DelayedFixture):
        async def execute(self, *args, **kwargs):
            pid = self.provider_id()
            active[pid] += 1
            peaks[pid] = max(peaks[pid], active[pid])
            try:
                return await super().execute(*args, **kwargs)
            finally:
                active[pid] -= 1

    service = SpiderService(str(tmp_path / "shared.db"), str(tmp_path / "runs"))
    tracker = Tracker()
    for index in range(5):
        service.provider_manager.register_adapter(CountedFixture(index, tracker, delay=.04))
    service.capability_registry.get_capability("SUBDOMAIN_DISCOVERY").default_providers = list(service.provider_manager.adapters)
    await service.start()
    try:
        cases = []
        for index in range(2):
            case = (await service.create_case("Synthetic shared limits"))["id"]
            await service.add_target(case, f"case{index}.test", T.DOMAIN)
            cases.append(case)
        runs = await asyncio.wait_for(asyncio.gather(*(service.investigate(case,
            ExecutionBudget(max_parallel_tasks=4, max_depth=0)) for case in cases)), 10)
        assert all(r["status"] == "COMPLETED" and r["budget_ledger"]["requests_count"] == 5 for r in runs)
        assert tracker.peak == 4 and tracker.active == 0
        assert set(peaks.values()) == {1} and not any(active.values())
    finally:
        await service.stop()
