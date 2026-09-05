import pytest
from spider.core.factory import create_spider_service
from spider.models.enums import ObservableType
from spider.models.budget import ExecutionBudget

@pytest.mark.asyncio
async def test_email_pipeline_finds_public_profiles_without_infrastructure_leakage(tmp_path):
    db_file = str(tmp_path / "email_test.db")
    service = create_spider_service(mode="production", db_path=db_file)
    await service.start()
    try:
        case = await service.create_case(name="Email Pipeline Test")
        case_id = case["id"]
        
        # Add EMAIL target
        email_target = "admin@example.com"
        await service.add_target(case_id, email_target, ObservableType.EMAIL, scope_authorized=True)
        
        # Run investigation with depth 2
        budget = ExecutionBudget(max_depth=0, max_entities=50)
        run_res = await service.investigate(case_id, budget=budget)
        assert run_res["status"] in ("COMPLETED", "PARTIAL")  # external sources can be unavailable
        assert run_res["observations_collected"] > 0
        
        entities = await service.get_case_entities(case_id)
        assertions = await service.get_case_assertions(case_id)
        
        # Personal mode may return public profile entities but must not turn the
        # email domain's infrastructure into personal findings.
        assert len(entities) >= 2, "Email investigation produced fewer than 2 entities"
        assert len(assertions) >= 1, "Email investigation produced 0 assertions"

        types = {e["type"] for e in entities}
        assert "EMAIL" in types
        assert "DOMAIN" not in types
        assert {"ACCOUNT", "URL"} & types
    finally:
        await service.stop()
