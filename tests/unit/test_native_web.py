import httpx
import pytest

from spider.models.budget import BudgetLedger, ExecutionBudget
from spider.models.enums import ObservableType
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage
from spider.providers.native.web import NativeWebMetadataAdapter


@pytest.mark.asyncio
async def test_authorized_web_metadata_keeps_only_allowlisted_response_fields():
    adapter = NativeWebMetadataAdapter()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, headers={
        "server": "fixture-server", "x-powered-by": "fixture-stack",
        "strict-transport-security": "max-age=1", "content-security-policy": "default-src 'self'",
        "set-cookie": "must-not-be-stored=secret"}, text="<title>Fixture site</title>"))
    result = await adapter.execute(
        NormalizedObservable(type=ObservableType.DOMAIN, value="example.test"),
        SourceLineage(case_id="case", run_id="run", task_id="task", provider_id="native_web", provider_version="1"),
        request_ledger=BudgetLedger(), execution_budget=ExecutionBudget(max_requests=1), transport=transport)

    assert result.outcome == "COMPLETED" and len(result.observations) == 1
    data = result.observations[0].raw_data
    assert data["http_status"] == 200 and data["title"] == "Fixture site"
    assert data["has_hsts"] is True and data["has_csp"] is True
    assert "set-cookie" not in data and "must-not-be-stored" not in result.raw_content.decode()
