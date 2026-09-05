import json
import httpx
import pytest
from sqlalchemy import select
from spider.models.enums import ObservableType as T
from spider.models.budget import ExecutionBudget
from spider.providers.native.public_profiles import PublicProfilesAdapter
from spider.storage.schema import EgressRecord
from spider.service.service import SpiderService
from spider.service.insights import CaseInsightsBuilder


@pytest.mark.asyncio
async def test_two_seeds_shared_account_cannot_leak_evidence_or_plaintext_ledger(tmp_path):
    def upstream(request):
        return httpx.Response(200, json={"login": request.url.path.rsplit("/", 1)[-1],
            "name": "Synthetic public display", "blog": "https://fixture.test"})
    service = SpiderService(db_path=str(tmp_path / "scope.db"), artifacts_dir=str(tmp_path / "runs"))
    service.provider_manager.register_adapter(PublicProfilesAdapter(httpx.MockTransport(upstream)))
    await service.start()
    try:
        case = await service.create_case("Scoped fixture")
        first = await service.add_target(case["id"], "fixture-alice", T.USERNAME)
        second = await service.add_target(case["id"], "fixture-bob", T.USERNAME)
        result = await service.investigate(case["id"], ExecutionBudget(max_depth=0))
        async with service.db_manager.session_factory() as session:
            default = await CaseInsightsBuilder.build_insights(session, case["id"], None)
            assert default["scope"]["selection_required"] and not default["public_profiles"]
            a = await CaseInsightsBuilder.build_insights(session, case["id"], None, first["id"])
            b = await CaseInsightsBuilder.build_insights(session, case["id"], None, second["id"])
            assert len(a["public_profiles"]) == len(b["public_profiles"]) == 1
            assert "fixture-bob" not in json.dumps(a["public_profiles"])
            assert set(a["scope"]["evidence_ids"]).isdisjoint(b["scope"]["evidence_ids"])
            for insight in (a, b):
                github = next(p for p in insight["provider_contributions"] if p["provider_id"] == "github_public")
                assert github["applicability"] == "APPLICABLE"
                assert github["execution_state"] == "CALLED"
                assert github["request_count"] == 1
                assert github["contributed"]
                uncover = next(p for p in insight["provider_contributions"] if p["provider_id"] == "uncover")
                assert uncover["applicability"] == "NOT_APPLICABLE"
                assert uncover["execution_state"] == "NOT_APPLICABLE"
                assert uncover["credential_state"] == "NOT_APPLICABLE"
            rows = list((await session.scalars(select(EgressRecord))).all())
            assert len(rows) == result["budget_ledger"]["requests_count"] == 2
            dumped = json.dumps([{c.name: str(getattr(r, c.name)) for c in EgressRecord.__table__.columns} for r in rows])
            assert "fixture-alice" not in dumped and "fixture-bob" not in dumped
            assert all(r.destination == "api.github.com" and r.authentication == "ANONYMOUS" for r in rows)
    finally:
        await service.stop()
