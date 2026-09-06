import pytest
from sqlalchemy import select

from spider.models.budget import BudgetLedger, ExecutionBudget
from spider.models.enums import ObservableType
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage
from spider.providers.uncover import api_access as access
from spider.providers.uncover.adapter import UncoverAdapter
from spider.service.insights import CaseInsightsBuilder
from spider.service.service import SpiderService
from spider.storage.schema import EgressRecord


@pytest.mark.asyncio
async def test_uncover_receipt_uses_verified_journal_and_credentialed_egress(tmp_path, monkeypatch):
    keys = {"SHODAN_API_KEY": "synthetic-shodan", "CENSYS_API_TOKEN": "synthetic-censys",
            "FOFA_KEY": "synthetic-fofa"}
    calls = []
    async def run_engine(engine, actual_keys, **kwargs):
        assert actual_keys[access.REQUIREMENTS[engine][0]] == keys[access.REQUIREMENTS[engine][0]]
        assert await kwargs["on_request"]({"kind": "request_permit", "sequence": 1,
            "destination": access.JOURNAL_DESTINATIONS[engine], "purpose": "internet_asset_search"})
        calls.append(engine)
        result = access.result_state(engine, "VALID", "SEARCH_VERIFIED", "search")
        result.update(results=[{"engine": engine, "ip": {
            "shodan": "192.0.2.1", "censys": "192.0.2.2", "fofa": "192.0.2.3"}[engine]}],
            request_journal=[{"sequence": 1, "method": "GET",
                "destination": access.JOURNAL_DESTINATIONS[engine],
                "purpose": "internet_asset_search", "http_status": 200, "outcome": "HTTP_200"}])
        return result
    monkeypatch.setattr(access, "run_engine", run_engine)
    service = SpiderService(db_path=str(tmp_path / "receipt.db"), artifacts_dir=str(tmp_path / "runs"))
    service.provider_manager.register_adapter(UncoverAdapter(
        binary_path=tmp_path / "uncover.exe", key_loader=lambda: keys))
    await service.start()
    try:
        case = await service.create_case("Receipt fixture")
        target = await service.add_target(case["id"], "example.test", ObservableType.DOMAIN,
                                          scope_authorized=True)
        await service.investigate(case["id"], ExecutionBudget(max_depth=0, max_requests=5))
        async with service.db_manager.session_factory() as session:
            insights = await CaseInsightsBuilder.build_insights(
                session, case["id"], None, target["id"])
        receipt = next(p for p in insights["provider_contributions"]
                       if p["provider_id"] == "uncover")
        assert receipt["applicability"] == "APPLICABLE"
        assert receipt["execution_state"] == "CALLED"
        assert receipt["request_count"] == 3
        assert receipt["contributed"]
        assert receipt["credential_state"] == "CONFIGURED"
        assert calls == ["shodan", "censys", "fofa"]
        async with service.db_manager.session_factory() as session:
            egress = list((await session.scalars(select(EgressRecord))).all())
        assert len(egress) == 3
        assert all(row.authentication == "CREDENTIALED" for row in egress)
        assert {row.destination for row in egress} == set(access.JOURNAL_DESTINATIONS.values())
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_uncover_stops_before_engine_that_would_exceed_request_budget(monkeypatch, tmp_path):
    keys = {"SHODAN_API_KEY": "synthetic-shodan", "CENSYS_API_TOKEN": "synthetic-censys",
            "FOFA_KEY": "synthetic-fofa"}
    calls = []
    async def run_engine(engine, _keys, **kwargs):
        assert await kwargs["on_request"]({"kind": "request_permit", "sequence": 1,
            "destination": access.JOURNAL_DESTINATIONS[engine], "purpose": "internet_asset_search"})
        calls.append(engine)
        result = access.result_state(engine, "VALID", "SEARCH_VERIFIED", "search")
        result["request_journal"] = [{"sequence": 1, "method": "GET",
            "destination": access.JOURNAL_DESTINATIONS[engine],
            "purpose": "internet_asset_search", "http_status": 200, "outcome": "HTTP_200"}]
        return result
    monkeypatch.setattr(access, "run_engine", run_engine)
    adapter = UncoverAdapter(binary_path=tmp_path / "uncover.exe", key_loader=lambda: keys)
    ledger, budget = BudgetLedger(), ExecutionBudget(max_requests=2)
    result = await adapter.execute(
        NormalizedObservable(type=ObservableType.DOMAIN, value="example.test"),
        SourceLineage(case_id="case", run_id="run", task_id="task", provider_id="uncover",
                      provider_version="v1.2.1"),
        request_ledger=ledger, execution_budget=budget)
    assert calls == ["shodan", "censys"]
    assert ledger.requests_count == result.metadata["request_count"] == 2
    assert result.metadata["engines"]["fofa"]["reason"] == "REQUEST_LIMIT"
    assert result.metadata["engines"]["fofa"]["state"] == "SKIPPED_BUDGET"
    assert result.outcome == "PARTIAL"
