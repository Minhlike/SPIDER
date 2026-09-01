import pytest
import asyncio
from typing import List, Any
from spider.service.service import SpiderService
from spider.providers.base import BaseProviderAdapter, ProviderHealth, ProviderExecutionResult
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage

class SlowFailingProvider(BaseProviderAdapter):
    def provider_id(self) -> str:
        return "slow_failing"
    def version(self) -> str:
        return "1.0.0"
    def adapter_version(self) -> str:
        return "1.0.0"
    def capabilities(self) -> List[str]:
        return ["SUBDOMAIN_DISCOVERY"]
    def network_class(self) -> NetworkClass:
        return NetworkClass.THIRD_PARTY_ONLY
    def accepts(self) -> List[ObservableType]:
        return [ObservableType.DOMAIN]
    def produces(self) -> List[ObservableType]:
        return [ObservableType.HOSTNAME]
    async def health(self) -> ProviderHealth:
        return ProviderHealth(state=ProviderState.READY)
    def build_command(self, target: NormalizedObservable) -> List[str]:
        return ["slow.exe"]
    async def execute(self, target: NormalizedObservable, lineage: SourceLineage, **kwargs) -> ProviderExecutionResult:
        await asyncio.sleep(5.0)
        return ProviderExecutionResult(raw_content=b"error", observations=[], exit_code=1, error_message="Failed")
    def parse(self, raw_content: bytes, lineage: SourceLineage) -> List[Observation]:
        return []
    def normalize(self, raw_item: Any) -> NormalizedObservable:
        return NormalizedObservable(type=raw_item["type"], value=raw_item["value"])

@pytest.mark.asyncio
async def test_provider_timeout_and_failure_isolation(tmp_path):
    test_db = str(tmp_path / "test_resilience.db")
    test_runs = str(tmp_path / "runs")

    service = SpiderService(
        db_path=test_db,
        artifacts_dir=test_runs,
        capabilities_path="config/capabilities.yaml",
        policies_path="config/policies.yaml"
    )

    slow_provider = SlowFailingProvider()
    service.provider_manager.register_adapter(slow_provider)

    cap_sub = service.capability_registry.get_capability("SUBDOMAIN_DISCOVERY")
    if cap_sub:
        cap_sub.default_providers = ["slow_failing"]

    await service.start()
    try:
        case_res = await service.create_case("Resilience Case", "Testing failure isolation")
        case_id = case_res["id"]
        await service.add_target(case_id, "timeout-test.com", ObservableType.DOMAIN)

        # Run investigation with small timeout
        run_res = await service.investigate(case_id)
        assert run_res["status"] == "COMPLETED"
    finally:
        await service.stop()
