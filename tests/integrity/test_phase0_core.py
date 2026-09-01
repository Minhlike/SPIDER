import pytest
import os
import shutil
from pathlib import Path
from spider.service.service import SpiderService
from spider.providers.fake.provider_a import FakeProviderA
from spider.providers.fake.provider_b import FakeProviderB
from spider.models.enums import ObservableType

@pytest.mark.asyncio
async def test_full_phase0_lifecycle_and_rebuild(tmp_path):
    test_db = str(tmp_path / "test_spider.db")
    test_runs = str(tmp_path / "runs")

    service = SpiderService(
        db_path=test_db,
        artifacts_dir=test_runs,
        capabilities_path="config/capabilities.yaml",
        policies_path="config/policies.yaml"
    )

    # Register fake providers
    provider_a = FakeProviderA()
    provider_b = FakeProviderB()
    service.provider_manager.register_adapter(provider_a)
    service.provider_manager.register_adapter(provider_b)

    # Update capability defaults to point to fake providers for this test
    cap_sub = service.capability_registry.get_capability("SUBDOMAIN_DISCOVERY")
    if cap_sub:
        cap_sub.default_providers = ["fake_a"]
    cap_infra = service.capability_registry.get_capability("INFRASTRUCTURE_DISCOVERY")
    if cap_infra:
        cap_infra.default_providers = ["fake_b"]

    await service.start()

    try:
        # 1. Create Case
        case_res = await service.create_case("Test Case 1", "Testing Phase 0 Core", tags=["test", "phase0"])
        case_id = case_res["id"]

        # 2. Add Seed Target
        target_res = await service.add_target(case_id, "example.com", ObservableType.DOMAIN, scope_authorized=True)
        assert target_res["canonical_value"] == "example.com"

        # 3. Run Investigation
        run_res = await service.investigate(case_id)
        assert run_res["status"] == "COMPLETED"
        assert run_res["tasks_executed"] > 0
        assert run_res["observations_collected"] > 0

        # 4. Check Entities & Assertions
        entities = await service.get_case_entities(case_id)
        assertions = await service.get_case_assertions(case_id)
        assert len(entities) >= 4  # example.com, api.example.com, 93.184.216.34, AS15133, etc.
        assert len(assertions) >= 3

        # 5. Test Explain Engine on first assertion
        asrt_id = assertions[0]["id"]
        explanation = await service.explain_assertion(asrt_id)
        assert explanation is not None
        assert explanation["assertion_id"] == asrt_id
        assert len(explanation["evidence"]) > 0
        assert explanation["evidence"][0]["raw_artifact_sha256"] is not None

        # 6. Verify Raw Artifacts exist on disk and match SHA256
        for ev in explanation["evidence"]:
            sha = ev["raw_artifact_sha256"]
            assert len(sha) == 64

        # 7. Test Graph Rebuild from append-only observations
        rebuild_res = await service.rebuild_case(case_id)
        assert rebuild_res["status"] == "SUCCESS"
        assert rebuild_res["entities_rebuilt"] == len(entities)
        assert rebuild_res["assertions_rebuilt"] == len(assertions)

        # 8. Test Graph Projection (NetworkX)
        metrics = await service.get_graph_summary(case_id)
        assert metrics["nodes_count"] == len(entities)
        assert metrics["edges_count"] == len(assertions)

    finally:
        await service.stop()
