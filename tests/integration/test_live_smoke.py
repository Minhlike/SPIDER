import pytest
from spider.core.factory import create_spider_service
from spider.models.enums import ObservableType
from spider.models.budget import ExecutionBudget
from spider.service.insights import CaseInsightsBuilder

@pytest.mark.asyncio
@pytest.mark.parametrize("target,obs_type", [
    ("admin@example.com", ObservableType.EMAIL),
    ("example.com", ObservableType.DOMAIN),
    ("93.184.216.34", ObservableType.IP_ADDRESS),
    ("octocat", ObservableType.USERNAME),
])
async def test_live_smoke_target(tmp_path, target, obs_type):
    db_file = str(tmp_path / f"smoke_{obs_type.value}.db")
    service = create_spider_service(mode="production", db_path=db_file)
    await service.start()
    try:
        case = await service.create_case(name=f"Smoke: {target}")
        case_id = case["id"]
        await service.add_target(case_id, target, obs_type, scope_authorized=True)
        budget = ExecutionBudget(max_depth=0, max_entities=10, max_runtime_seconds=25, username_site_limit=50)
        run_res = await service.investigate(case_id, budget=budget)
        assert run_res["status"] in ("COMPLETED", "PARTIAL", "FAILED")
        assert run_res["tasks_executed"] > 0

        entities = await service.get_case_entities(case_id)
        assert len(entities) >= 1
        
        async with service.db_manager.session_factory() as session:
            insights = await CaseInsightsBuilder.build_insights(session, case_id, None)
            assert insights["case_id"] == case_id
            assert "provider_contributions" in insights
            assert "empty_reason" in insights
            if obs_type == ObservableType.USERNAME:
                sources = [p for p in insights["provider_contributions"] if p["tasks_count"]]
                assert any(p["provider_id"] == "github_public" for p in sources)
                assert any(p["provider_id"] == "maigret" and p.get("coverage", {}).get("checked", 0) > 0 for p in sources)
                assert any(e["type"] == "ACCOUNT" for e in entities), "Seed alone is not username discovery"
    finally:
        await service.stop()
