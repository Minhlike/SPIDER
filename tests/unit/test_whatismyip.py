import json

import httpx
import pytest

from spider.models.budget import BudgetLedger, ExecutionBudget
from spider.models.enums import ObservableType
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage
from spider.providers.whatismyip.adapter import (
    WhatIsMyIPAdapter,
    check_api_key,
    fetch_public_address,
)

SENTINEL = "synthetic-whatismyip-secret-never-log"


def lineage():
    return SourceLineage(case_id="case", run_id="run", task_id="task",
                         provider_id="whatismyip", provider_version="v1",
                         parent_observable_value="8.8.8.8",
                         parent_observable_type=ObservableType.IP_ADDRESS)


@pytest.mark.asyncio
async def test_adapter_uses_header_and_normalizes_lookup_and_proxy(caplog):
    seen = []

    def upstream(request):
        seen.append((request.url.path, request.headers.get("x-api-key")))
        assert "key" not in request.url.params
        if request.url.path.startswith("/ip-address-lookup/"):
            return httpx.Response(200, json={
                "ip": "8.8.8.8", "country": "United States", "region": "California",
                "city": "Mountain View", "postal_code": "94035", "isp": "Google LLC",
                "asn": "AS15169", "latitude": 37.4, "longitude": -122.1,
                "time_zone": "-08:00",
            })
        return httpx.Response(200, json={
            "is_proxy": False, "proxy_type": "none",
            "proxy_type_description": "No proxy detected", "proxy_range": None,
        })

    ledger, budget = BudgetLedger(), ExecutionBudget(max_requests=2)
    result = await WhatIsMyIPAdapter(lambda: SENTINEL).execute(
        NormalizedObservable(type=ObservableType.IP_ADDRESS, value="8.8.8.8"),
        lineage(), request_ledger=ledger, execution_budget=budget,
        transport=httpx.MockTransport(upstream),
    )

    assert result.outcome == "COMPLETED"
    assert ledger.requests_count == 2
    assert [item[0] for item in seen] == [
        "/ip-address-lookup/8.8.8.8", "/proxy-check/8.8.8.8"]
    assert all(value == SENTINEL for _, value in seen)
    assert {obs.observable.type for obs in result.observations} == {
        ObservableType.IP_ADDRESS, ObservableType.ASN, ObservableType.ORGANIZATION}
    record = result.observations[0].raw_data
    assert record["city"] == "Mountain View"
    assert record["is_proxy"] is False
    assert record["proxy_type_description"] == "No proxy detected"
    assert SENTINEL not in result.raw_content.decode()
    assert SENTINEL not in result.model_dump_json()
    assert SENTINEL not in caplog.text


@pytest.mark.asyncio
async def test_private_address_never_leaves_machine():
    calls = []
    transport = httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(500))
    result = await WhatIsMyIPAdapter(lambda: SENTINEL).execute(
        NormalizedObservable(type=ObservableType.IP_ADDRESS, value="192.168.1.9"),
        lineage(), transport=transport)
    assert result.outcome == "COMPLETED"
    assert result.metadata["collection_state"] == "LOCAL_ONLY_ADDRESS"
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status,state", [
    (401, "INVALID_KEY"), (403, "DISABLED_KEY"), (429, "QUOTA_LIMIT"),
    (503, "NETWORK_ERROR"),
])
async def test_credential_check_classifies_failures_without_echo(status, state, caplog):
    result = await check_api_key(SENTINEL, transport=httpx.MockTransport(
        lambda request: httpx.Response(status, json={"message": SENTINEL})))
    assert result["state"] == state
    assert SENTINEL not in json.dumps(result)
    assert SENTINEL not in caplog.text


@pytest.mark.asyncio
async def test_current_public_ip_response_is_validated():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"ip": "8.8.8.8"}))
    assert await fetch_public_address(SENTINEL, 4, transport=transport) == {
        "ip": "8.8.8.8", "version": 4}
    bad = httpx.MockTransport(lambda request: httpx.Response(200, json={"ip": "127.0.0.1"}))
    with pytest.raises(ValueError, match="PUBLIC_ADDRESS_UNAVAILABLE"):
        await fetch_public_address(SENTINEL, 4, transport=bad)


def test_parser_rejects_mismatched_or_invalid_ip():
    adapter = WhatIsMyIPAdapter(lambda: SENTINEL)
    assert adapter.parse(b'{"lookup":{"ip":"not-an-ip"}}', lineage()) == []


@pytest.mark.asyncio
async def test_health_is_fail_closed_until_live_check_has_evidence():
    configured = await WhatIsMyIPAdapter(lambda: SENTINEL).health()
    missing = await WhatIsMyIPAdapter(lambda: "").health()
    assert configured.state.value == "DEGRADED"
    assert configured.credential_state == "UNTESTED"
    assert configured.live_verified is False and configured.contract_verified is False
    assert missing.state.value == "MISSING_CREDENTIAL"
