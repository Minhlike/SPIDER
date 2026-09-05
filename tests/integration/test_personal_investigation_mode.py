import pytest

from spider.models.budget import ExecutionBudget
from spider.models.enums import NetworkClass, ObservableType, ProviderState
from spider.providers.base import BaseProviderAdapter, ProviderExecutionResult, ProviderHealth
from spider.service.service import SpiderService


class RecordingAdapter(BaseProviderAdapter):
    request_budget_supported = True

    def __init__(self, provider_id, capabilities, accepted, calls):
        self._provider_id = provider_id
        self._capabilities = capabilities
        self._accepted = accepted
        self._calls = calls

    def provider_id(self): return self._provider_id
    def version(self): return "fixture"
    def adapter_version(self): return "fixture"
    def capabilities(self): return self._capabilities
    def accepts(self): return self._accepted
    def produces(self): return []
    def network_class(self): return NetworkClass.THIRD_PARTY_ONLY
    async def health(self): return ProviderHealth(state=ProviderState.READY)
    def build_command(self, target): return []
    def normalize(self, raw_item): raise NotImplementedError
    def parse(self, raw_content, lineage): return []

    async def execute(self, target, lineage, **kwargs):
        self._calls.append(self._provider_id)
        return ProviderExecutionResult(raw_content=b"{}", observations=[], outcome="COMPLETED")


@pytest.mark.asyncio
async def test_personal_email_run_never_dispatches_dns_or_infrastructure(tmp_path):
    calls = []
    service = SpiderService(db_path=str(tmp_path / "personal.db"),
                            artifacts_dir=str(tmp_path / "runs"))
    service.provider_manager.register_adapter(RecordingAdapter(
        "github_public", ["PUBLIC_PROFILE_LOOKUP"],
        [ObservableType.EMAIL, ObservableType.USERNAME], calls))
    service.provider_manager.register_adapter(RecordingAdapter(
        "native_dns", ["DNS_ENUMERATION", "MAIL_INFRASTRUCTURE"],
        [ObservableType.EMAIL, ObservableType.DOMAIN], calls))
    service.provider_manager.register_adapter(RecordingAdapter(
        "coccoc_browser", ["BROWSER_PERSONAL_DISCOVERY"],
        [ObservableType.EMAIL, ObservableType.USERNAME], calls))
    await service.start()
    try:
        case = await service.create_case("Personal email fixture")
        await service.add_target(case["id"], "owner@example.invalid", ObservableType.EMAIL)
        result = await service.investigate(case["id"], ExecutionBudget(
            max_depth=1, max_requests=5, diminishing_returns_cutoff=10))
        assert calls == ["github_public"]
        assert result["investigation_mode"] == "PERSONAL_FOOTPRINT"
        assert result["observations_collected"] == 0
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_browser_provider_only_dispatches_after_explicit_opt_in(tmp_path):
    calls = []
    service = SpiderService(db_path=str(tmp_path / "browser-opt-in.db"),
                            artifacts_dir=str(tmp_path / "runs"))
    service.provider_manager.register_adapter(RecordingAdapter(
        "coccoc_browser", ["BROWSER_PERSONAL_DISCOVERY"],
        [ObservableType.USERNAME], calls))
    await service.start()
    try:
        case = await service.create_case("Browser opt-in fixture")
        await service.add_target(case["id"], "fixture-user", ObservableType.USERNAME)
        without_browser = await service.investigate(case["id"], ExecutionBudget(
            max_depth=0, diminishing_returns_cutoff=10))
        assert calls == [] and without_browser["browser_assisted"] is False

        with_browser = await service.investigate(case["id"], ExecutionBudget(
            max_depth=0, diminishing_returns_cutoff=10), browser_assisted=True)
        assert calls == ["coccoc_browser"]
        assert with_browser["browser_assisted"] is True
    finally:
        await service.stop()
