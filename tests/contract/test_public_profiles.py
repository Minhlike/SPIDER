import json

import httpx
import pytest

from spider.models.enums import ObservableType
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage
from spider.providers.native.public_profiles import PublicProfilesAdapter
from spider.providers.maigret.adapter import MaigretAdapter


def lineage(provider="github_public", target="owner@example.org"):
    return SourceLineage(case_id="c", run_id="r", task_id="t", provider_id=provider,
                         provider_version="test", parent_observable_value=target)


@pytest.mark.asyncio
async def test_email_match_requires_public_profile_evidence():
    requested = []
    def respond(request):
        requested.append(request.url.path)
        if request.url.path == "/search/users":
            assert request.url.params["q"] == '"owner@example.org" in:email'
            return httpx.Response(200, json={"total_count": 3, "incomplete_results": False,
                "items": [{"login": "matching"}, {"login": "different"}, {"login": "hidden"}]})
        login = request.url.path.rsplit("/", 1)[1]
        email = {"matching": "owner@example.org", "different": "elsewhere@example.org", "hidden": None}[login]
        return httpx.Response(200, json={"login": login, "email": email, "name": "Public Test Name",
            "bio": "Synthetic public profile", "blog": "https://example.org", "private_field": "must-not-retain"})
    adapter = PublicProfilesAdapter(httpx.MockTransport(respond))
    result = await adapter.execute(NormalizedObservable(type=ObservableType.EMAIL, value="owner@example.org"), lineage())
    assert result.outcome == "COMPLETED"
    assert result.metadata["profiles_checked"] == 3
    assert len(result.observations) == 3
    assert result.observations[0].observable.canonical_value == "matching@github"
    assert all(o.raw_data["match_basis"] == "exact_public_email" for o in result.observations)
    assert b"must-not-retain" not in result.raw_content
    assert len(requested) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 429, 500])
async def test_unavailable_search_is_not_no_findings(status):
    adapter = PublicProfilesAdapter(httpx.MockTransport(lambda request: httpx.Response(status,
        json={"message": "secret-token must not escape"})))
    result = await adapter.execute(NormalizedObservable(type=ObservableType.EMAIL, value="owner@example.org"), lineage())
    assert result.outcome == "PARTIAL" and result.error_message
    assert not result.observations
    assert "secret-token" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_incomplete_search_preserves_partial_status():
    adapter = PublicProfilesAdapter(httpx.MockTransport(lambda request: httpx.Response(200,
        json={"total_count": 0, "items": [], "incomplete_results": True})))
    result = await adapter.execute(NormalizedObservable(type=ObservableType.EMAIL, value="owner@example.org"), lineage())
    assert result.outcome == "PARTIAL"


@pytest.mark.parametrize("status", ["Available", "Unknown", "Illegal", "Not found", "", "ok"])
def test_url_is_not_a_positive_status(status):
    raw = json.dumps({"sitename": "Synthetic", "url_user": "https://example.org/user",
                      "status": {"status": status}}).encode()
    assert not MaigretAdapter().parse(raw, lineage("maigret", "user"))


def test_nested_claimed_contract_and_partial_line():
    raw = (json.dumps({"sitename": "Synthetic", "url_user": "https://example.org/user",
                       "status": {"status": "Claimed", "username": "user"}}) + '\n{"unfinished":').encode()
    observations = MaigretAdapter().parse(raw, lineage("maigret", "user"))
    assert len(observations) == 2
    assert observations[0].raw_data["match_basis"] == "username_only"


def test_non_web_positive_url_is_rejected():
    raw = b'{"sitename":"Bad","url_user":"javascript:alert(1)","status":{"status":"Claimed"}}'
    assert not MaigretAdapter().parse(raw, lineage("maigret", "user"))
