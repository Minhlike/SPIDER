import asyncio
import pytest
from spider.models.budget import BudgetLedger, ExecutionBudget, RequestBudgetExceeded
from spider.models.enums import ObservableType as T
from spider.models.execution import TaskRun
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage
from spider.providers.base import ProviderExecutionResult
from spider.providers.fake.provider_a import FakeProviderA
from spider.service.service import SpiderService
from spider.storage.schema import ProviderRunRecord, TaskRunRecord


@pytest.mark.asyncio
async def test_overlapping_tasks_record_own_requests_and_preserve_shared_cap(tmp_path):
    both_started, release = asyncio.Event(), asyncio.Event()
    started = []

    class Adapter(FakeProviderA):
        def __init__(self, name):
            self.name = name

        def provider_id(self):
            return self.name

        async def execute(self, target, lineage, **options):
            ledger = options["request_ledger"]
            ledger.request(options["execution_budget"], self.provider_id())
            started.append(lineage.task_id)
            if len(started) == 2:
                both_started.set()
            await release.wait()
            if lineage.task_id == "second":
                ledger.request(options["execution_budget"], self.provider_id(), kind="retry")
            return ProviderExecutionResult(raw_content=b"{}", observations=[], outcome="COMPLETED")

    service = SpiderService(str(tmp_path / "receipts.db"), str(tmp_path / "runs"))
    for name in ("first", "second"):
        service.provider_manager.register_adapter(Adapter(name))
    await service.start()
    try:
        case = await service.create_case("Synthetic receipts")
        async def seed_run(session):
            session.add(ProviderRunRecord(id="run", case_id=case["id"], status="RUNNING"))
        await service.db_writer.submit(seed_run)
        ledger, budget = BudgetLedger(), ExecutionBudget(max_requests=3)
        async def call(task_id):
            task = TaskRun(id=task_id, case_id=case["id"], run_id="run", provider_id=task_id,
                capability="SUBDOMAIN_DISCOVERY", execution_key_hash=task_id,
                target_observable_value="example.invalid")
            lineage = SourceLineage(case_id=case["id"], run_id="run", task_id=task_id,
                provider_id=task_id, provider_version="1")
            return await service.provider_manager.execute_task(task,
                NormalizedObservable(type=T.DOMAIN, value="example.invalid"), lineage,
                request_ledger=ledger, execution_budget=budget)
        pending = [asyncio.create_task(call(task_id)) for task_id in ("first", "second")]
        await asyncio.wait_for(both_started.wait(), 5)
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*pending), 5)
        assert [result.metadata["request_count"] for result in results] == [1, 2]
        assert ledger.requests_count == 3
        assert [e["task_id"] for e in ledger.request_events].count("first") == 1
        assert [e["task_id"] for e in ledger.request_events].count("second") == 2
        with pytest.raises(RequestBudgetExceeded):
            ledger.for_task("third").request(budget, "fake_a")
        assert ledger.count_for_task("third") == 0
        async with service.db_manager.session_factory() as session:
            rows = [await session.get(TaskRunRecord, task_id) for task_id in ("first", "second")]
            assert [row.metadata_json["request_count"] for row in rows] == [1, 2]
        assert "example.invalid" not in ledger.model_dump_json()
    finally:
        release.set()
        await service.stop()
