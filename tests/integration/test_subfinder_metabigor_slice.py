import pytest
from pathlib import Path
from spider.service.service import SpiderService
from spider.providers.subfinder.adapter import SubfinderAdapter
from spider.providers.metabigor.adapter import MetabigorAdapter
from spider.models.enums import ObservableType, AssertionType
from spider.models.budget import ExecutionBudget

@pytest.mark.asyncio
async def test_vertical_slice_subfinder_and_metabigor(tmp_path):
    test_db = str(tmp_path / "slice.db")
    test_runs = str(tmp_path / "runs")

    service = SpiderService(
        db_path=test_db,
        artifacts_dir=test_runs,
        capabilities_path="config/capabilities.yaml",
        policies_path="config/policies.yaml"
    )

    # Subclass adapters with mock execution for deterministic vertical slice integration test
    class MockSubfinder(SubfinderAdapter):
        request_budget_supported = True  # Fixture parsing only; no subprocess/network.
        async def execute(self, target, lineage, **kwargs):
            raw = Path("tests/fixtures/subfinder/v2.16.0_sample.jsonl").read_bytes()
            obs = self.parse(raw, lineage)
            return type(self)._create_res(self, raw, obs)
        def _create_res(self, raw, obs):
            from spider.providers.base import ProviderExecutionResult
            return ProviderExecutionResult(raw_content=raw, observations=obs, exit_code=0, mime_type="application/x-ndjson")

    class MockMetabigor(MetabigorAdapter):
        request_budget_supported = True
        async def execute(self, target, lineage, **kwargs):
            raw = Path("tests/fixtures/metabigor/v2.2.0_sample.json").read_bytes()
            obs = self.parse(raw, lineage)
            from spider.providers.base import ProviderExecutionResult
            return ProviderExecutionResult(raw_content=raw, observations=obs, exit_code=0, mime_type="application/json")

    subfinder = MockSubfinder(binary_path="tools/subfinder/subfinder.exe")
    metabigor = MockMetabigor(binary_path="tools/metabigor/metabigor.exe")

    service.provider_manager.register_adapter(subfinder)
    service.provider_manager.register_adapter(metabigor)

    # Ensure capability mapping
    cap_sub = service.capability_registry.get_capability("SUBDOMAIN_DISCOVERY")
    if cap_sub:
        cap_sub.default_providers = ["subfinder"]
    cap_infra = service.capability_registry.get_capability("INFRASTRUCTURE_DISCOVERY")
    if cap_infra:
        cap_infra.default_providers = ["metabigor"]

    await service.start()

    try:
        # 1. Create Case
        case_res = await service.create_case("Vertical Slice Case", "Testing DOMAIN -> HOSTNAME -> IP -> ASN -> CIDR")
        case_id = case_res["id"]

        # 2. Add Target
        await service.add_target(case_id, "example.com", ObservableType.DOMAIN, scope_authorized=True)

        # 3. Investigate with depth 2 to allow fan-out from DOMAIN -> HOSTNAME/IP -> ASN/CIDR
        budget = ExecutionBudget(max_depth=2, max_entities=100)
        run_res = await service.investigate(case_id, budget=budget)
        assert run_res["status"] == "COMPLETED"

        # 4. Verify entities across full vertical slice
        entities = await service.get_case_entities(case_id)
        ent_types = {e["type"] for e in entities}
        assert "DOMAIN" in ent_types
        assert "HOSTNAME" in ent_types
        assert "IP_ADDRESS" in ent_types
        assert "ASN" in ent_types
        assert "CIDR" in ent_types
        assert "ORGANIZATION" in ent_types

        # 5. Verify assertions
        assertions = await service.get_case_assertions(case_id)
        asrt_types = {a["assertion_type"] for a in assertions}
        assert AssertionType.SUBDOMAIN_OF.value in asrt_types
        assert AssertionType.RESOLVES_TO.value in asrt_types
        assert AssertionType.BELONGS_TO_ASN.value in asrt_types
        assert AssertionType.HOSTED_ON.value in asrt_types

        # 6. Verify explanation of ASN assertion
        asn_asrt = next(a for a in assertions if a["assertion_type"] == AssertionType.BELONGS_TO_ASN.value)
        explanation = await service.explain_assertion(asn_asrt["id"])
        assert explanation is not None
        assert explanation["source_entity"]["type"] == "IP_ADDRESS"
        assert explanation["target_entity"]["type"] == "ASN"
        assert explanation["rule"] == {
            "id": "ADDRESS_BELONGS_TO_ASN", "version": "1.0.0",
            "registry_version": "1.0.0", "evidence_requirement": "DIRECT_OBSERVATION"}
        assert explanation["claim_lifecycle"]["state"] == "SUPPORTED_RELATION"
        assert explanation["justification_dag"]["acyclic"] is True
        assert explanation["justification_dag"]["proof_complete"] is True
        assert any(edge["kind"] == "DERIVES" for edge in explanation["justification_dag"]["edges"])
        node_ids = {node["id"] for node in explanation["justification_dag"]["nodes"]}
        assert len(node_ids) == len(explanation["justification_dag"]["nodes"])
        assert all(edge["from"] in node_ids and edge["to"] in node_ids
                   for edge in explanation["justification_dag"]["edges"])
        assert len(explanation["evidence"]) > 0

        # 7. Test complete rebuild
        rebuild_res = await service.rebuild_case(case_id)
        assert rebuild_res["status"] == "SUCCESS"
        assert rebuild_res["entities_rebuilt"] == len(entities)
        assert rebuild_res["assertions_rebuilt"] == len(assertions)

    finally:
        await service.stop()
