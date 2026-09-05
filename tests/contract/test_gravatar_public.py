import json

import httpx
import pytest

from spider.models.budget import BudgetLedger, ExecutionBudget
from spider.models.enums import ObservableType
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage
from spider.providers.native.gravatar import GravatarPublicProfileAdapter, gravatar_email_hash


EMAIL = "owner@example.invalid"


def lineage():
    return SourceLineage(case_id="case", run_id="run", task_id="task",
        provider_id="gravatar_public", provider_version="v3",
        parent_observable_value=EMAIL, parent_observable_type=ObservableType.EMAIL)


def target():
    return NormalizedObservable(type=ObservableType.EMAIL, value=f"  {EMAIL.upper()}  ")


@pytest.mark.asyncio
async def test_public_profile_is_exact_hash_link_with_allowlisted_artifact():
    seen = []
    expected_hash = gravatar_email_hash(EMAIL)

    def upstream(request):
        seen.append(request)
        return httpx.Response(200, json={
            "hash": expected_hash,
            "profile_url": "https://gravatar.com/public-owner?tracking=discard#fragment",
            "display_name": "Public Owner",
            "description": f"Contact {EMAIL} for a secret-value",
            "location": "Viet Nam",
            "job_title": "Researcher",
            "company": "Example",
            "links": [{"label": "Site", "url": "https://example.org/about?token=discard"}],
            "verified_accounts": [
                {"service_type": "instagram", "service_label": "Instagram",
                 "url": "https://instagram.com/public.owner?ref=discard", "is_hidden": False},
                {"service_type": "threads", "service_label": "Threads",
                 "url": "https://threads.net/@hidden-owner", "is_hidden": True},
            ],
            "private_field": "must-not-retain",
        })

    ledger, budget = BudgetLedger(), ExecutionBudget(max_requests=3)
    result = await GravatarPublicProfileAdapter(httpx.MockTransport(upstream)).execute(
        target(), lineage(), request_ledger=ledger, execution_budget=budget)

    assert result.outcome == "COMPLETED"
    assert result.metadata["identifier_disclosed"] == "SHA256_EMAIL"
    assert result.metadata["requests"] == ledger.requests_count == 1
    assert len(seen) == 1
    assert seen[0].url.path == f"/v3/profiles/{expected_hash}"
    assert not seen[0].url.query
    assert len(result.observations) == 4
    assert {o.observable.canonical_value for o in result.observations} == {
        "public-owner@gravatar", "https://gravatar.com/public-owner",
        "public.owner@instagram", "https://instagram.com/public.owner",
    }
    serialized = result.raw_content.decode()
    assert EMAIL not in serialized.casefold()
    assert "private_field" not in serialized
    assert "tracking" not in serialized and "token=discard" not in serialized
    assert "hidden-owner" not in serialized
    assert "[redacted-email]" in serialized
    rows = json.loads(serialized)["profiles"]
    assert rows[0]["match_basis"] == "email_hash_public_profile"
    assert rows[1]["verification_state"] == "SERVICE_VERIFIED_LINK"


@pytest.mark.asyncio
async def test_404_is_scoped_negative_not_global_email_negative():
    adapter = GravatarPublicProfileAdapter(httpx.MockTransport(
        lambda request: httpx.Response(404, json={"message": "not found"})))
    result = await adapter.execute(target(), lineage())
    assert result.outcome == "COMPLETED"
    assert result.metadata["specific_negative_verified"] is True
    assert result.metadata["collection_reason"] == "NO_PUBLIC_PRIMARY_EMAIL_PROFILE"
    assert not result.observations
    assert result.raw_content == b'{"profiles":[]}'


@pytest.mark.asyncio
@pytest.mark.parametrize("status,reason", [
    (403, "ACCESS_DENIED"), (429, "RATE_LIMIT"), (503, "UPSTREAM_ERROR")
])
async def test_unavailable_states_are_unknown_not_negative(status, reason):
    adapter = GravatarPublicProfileAdapter(httpx.MockTransport(
        lambda request: httpx.Response(status, json={"secret": EMAIL})))
    result = await adapter.execute(target(), lineage())
    assert result.outcome == "PARTIAL"
    assert result.metadata["specific_negative_verified"] is False
    assert result.metadata["collection_reason"] == reason
    assert EMAIL not in result.model_dump_json().casefold()


@pytest.mark.asyncio
async def test_wrong_response_hash_fails_closed_without_profile_evidence():
    adapter = GravatarPublicProfileAdapter(httpx.MockTransport(lambda request: httpx.Response(200, json={
        "hash": "0" * 64, "profile_url": "https://gravatar.com/wrong",
        "display_name": "Wrong"
    })))
    result = await adapter.execute(target(), lineage())
    assert result.outcome == "PARTIAL"
    assert result.metadata["collection_reason"] == "UNEXPECTED_RESPONSE"
    assert not result.observations


@pytest.mark.asyncio
async def test_oversized_or_wrong_input_never_becomes_evidence():
    calls = 0
    def oversized(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b'{' + b' ' * 262_145 + b'}')
    adapter = GravatarPublicProfileAdapter(httpx.MockTransport(oversized))
    result = await adapter.execute(target(), lineage())
    assert result.outcome == "PARTIAL"
    assert result.metadata["collection_reason"] == "NETWORK_OR_RESPONSE_ERROR"
    assert not result.observations and calls == 1

    wrong = await adapter.execute(
        NormalizedObservable(type=ObservableType.USERNAME, value="owner"), lineage())
    assert wrong.outcome == "FAILED"
    assert wrong.metadata["collection_reason"] == "UNSUPPORTED_INPUT_TYPE"
    assert calls == 1
