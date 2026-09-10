import asyncio
import json

import pytest

from spider.models.enums import ObservableType
from spider.models.provenance import SourceLineage
from spider.providers.browser.coccoc import (
    CocCocBrowserAdapter, apply_negative_control, classify_direct_candidate, classify_direct_result,
    apply_indexed_profile_candidates, browser_start_reason, candidate_has_username, coccoc_profile,
    coccoc_search_url, host_matches, indexed_profile_candidates,
    safe_result_url, select_search_candidate,
)


def test_profile_selection_is_bounded_to_chromium_profile_names(tmp_path):
    (tmp_path / "Default").mkdir()
    (tmp_path / "Local State").write_text(json.dumps({"profile": {"last_used": "../Secrets"}}),
                                           encoding="utf-8")
    assert coccoc_profile(tmp_path) == "Default"


def test_direct_candidate_requires_host_path_and_non_login_response():
    assert classify_direct_candidate("instagram.com", "alice", 200,
        "https://www.instagram.com/alice/", "Alice", "Public profile for alice") == "CANDIDATE"
    assert classify_direct_candidate("instagram.com", "alice", 200,
        "https://www.instagram.com/accounts/login/", "Log in", "Log in") == "LOGIN_REQUIRED"
    assert classify_direct_candidate("instagram.com", "alice", 404,
        "https://www.instagram.com/alice/", "Not found", "") == "NOT_FOUND"
    assert not host_matches("https://instagram.com.evil.invalid/alice", "instagram.com")
    assert not host_matches("https://user:secret@instagram.com/alice", "instagram.com")
    assert safe_result_url("https://instagram.com/alice?token=secret#part") == \
        "https://instagram.com/alice"


def test_direct_classifier_uses_declared_profile_url_and_preserves_access_failures():
    assert classify_direct_result("threads.com", "alice", 200,
        "https://www.threads.com/@alice", "Alice on Threads", "Public posts by @alice",
        ["https://www.threads.com/@alice"])[0] == "CANDIDATE"
    assert classify_direct_result("tiktok.com", "alice", 429,
        "https://www.tiktok.com/@alice", "TikTok", "Too many requests")[0] == "RATE_LIMITED"
    assert classify_direct_result("tiktok.com", "alice", 403,
        "https://www.tiktok.com/@alice", "Security check", "captcha")[0] == "BLOCKED"
    assert classify_direct_result("instagram.com", "alice", 403,
        "https://www.instagram.com/alice/", "Access check",
        "This page isn't available until you log in")[0] == "BLOCKED"
    assert classify_direct_result("threads.com", "alice", 200,
        "https://www.threads.com/@alice", "Threads", "Generic application shell",
        ["https://www.threads.com/@alice"])[0] == "UNKNOWN"


def test_coccoc_search_url_encodes_query_and_account_requires_path_match():
    assert coccoc_search_url('site:zalo.me "alice doe"') == \
        "https://coccoc.com/search?query=site%3Azalo.me+%22alice+doe%22"
    assert candidate_has_username("https://www.instagram.com/alice/", "alice")
    assert not candidate_has_username("https://www.instagram.com/notalice/", "alice")
    assert not candidate_has_username("https://www.tiktok.com/@alice/video/123", "alice")
    assert not candidate_has_username("https://x.com/alice/status/123", "alice")
    assert candidate_has_username("https://www.linkedin.com/in/alice/", "alice")
    assert not candidate_has_username("https://zalo.me/s/article-123", "alice")


def test_indexed_profile_fallback_keeps_explicit_absence_and_marks_search_candidate():
    rows = [
        {"source": "Instagram", "state": "LOGIN_REQUIRED", "reason": "LOGIN_WALL"},
        {"source": "Threads", "state": "NOT_FOUND", "reason": "HTTP_NOT_FOUND"},
    ]
    links = ["https://www.instagram.com/alice/", "https://www.threads.com/@alice"]

    candidates = indexed_profile_candidates(links, "alice")
    merged = apply_indexed_profile_candidates(rows, candidates, "COCCOC_SEARCH_RESULT")

    assert merged[0]["state"] == "LOGIN_REQUIRED"
    assert merged[0]["reason"] == "LOGIN_WALL"
    assert merged[1]["kind"] == "search_lead"
    assert merged[1]["state"] == "CANDIDATE"
    assert merged[1]["direct_outcome"] == "LOGIN_REQUIRED"
    assert merged[2]["state"] == "NOT_FOUND"


def test_indexed_profile_candidates_reject_posts_and_substring_handles():
    links = [
        "https://www.instagram.com/notalice/",
        "https://www.tiktok.com/@alice/video/123",
        "https://www.threads.com/@alice/post/ABC",
    ]
    assert indexed_profile_candidates(links, "alice") == {}


def test_email_search_candidate_cannot_be_proved_by_query_echo():
    unrelated = [{"href": "https://zalo.me/s/public-article", "text": "Public article"}]
    matching = [{"href": "https://zalo.me/s/public-article",
                 "text": "Contact owner@example.test"}]
    assert select_search_candidate(unrelated, "zalo.me", "owner@example.test", True) is None
    assert select_search_candidate(matching, "zalo.me", "owner@example.test", True) == \
        "https://zalo.me/s/public-article"


def test_negative_control_can_promote_only_a_differential_response():
    row = {"state": "UNKNOWN", "reason": "INSUFFICIENT_PAGE_SIGNALS"}
    promoted = apply_negative_control(row, "NOT_FOUND")
    assert promoted["state"] == "CANDIDATE"
    assert promoted["reason"] == "NEGATIVE_CONTROL_DIFFERENTIAL"
    generic = apply_negative_control(row, "CANDIDATE")
    assert generic["state"] == "UNKNOWN" and generic["reason"] == "NON_UNIQUE_RESPONSE"


@pytest.mark.parametrize(("message", "state"), [
    ("User data directory is already in use", "PROFILE_IN_USE"),
    ("Executable doesn't exist", "MISSING_RUNTIME"),
    ("Target page, context or browser has been closed", "BROWSER_CLOSED"),
    ("opaque Playwright failure", "BROWSER_START_FAILED"),
])
def test_browser_start_failure_has_a_fixed_safe_reason(message, state):
    assert browser_start_reason(RuntimeError(message)) == state


@pytest.mark.asyncio
async def test_direct_sources_use_at_most_three_parallel_tabs(monkeypatch):
    adapter = CocCocBrowserAdapter()
    active = 0
    peak = 0

    async def inspect(*_args):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1
        return {"state": "NOT_FOUND", "reason": "HTTP_NOT_FOUND", "http_status": 404}

    monkeypatch.setattr(adapter, "_inspect_direct_source", inspect)
    rows = await adapter._collect_direct_sources(None, "alice", 1000, lambda: False, 3)
    assert len(rows) == 8 and peak == 3


def test_parser_keeps_candidates_unverified_and_rejects_unlisted_hosts():
    raw = b'\n'.join([
        json.dumps({"source": "Instagram", "state": "CANDIDATE",
                    "url": "https://www.instagram.com/alice/"}).encode(),
        json.dumps({"source": "Fake", "state": "CANDIDATE",
                    "url": "https://evil.invalid/alice"}).encode(),
    ])
    lineage = SourceLineage(case_id="c", run_id="r", task_id="t",
        provider_id="coccoc_browser", provider_version="local-coccoc",
        parent_observable_value="alice", parent_observable_type=ObservableType.USERNAME)
    observations = CocCocBrowserAdapter().parse(raw, lineage)
    assert len(observations) == 2
    assert all(obs.raw_data["identity_verified"] is False for obs in observations)
    assert {obs.confidence for obs in observations} == {0.55}


def test_search_result_creates_account_only_for_a_profile_shaped_url():
    raw = b'\n'.join([
        json.dumps({"source": "Instagram", "state": "CANDIDATE",
                    "reason": "COCCOC_SEARCH_RESULT", "account_candidate": True,
                    "url": "https://www.instagram.com/alice/"}).encode(),
        json.dumps({"source": "Zalo", "state": "CANDIDATE",
                    "reason": "COCCOC_SEARCH_RESULT", "account_candidate": False,
                    "url": "https://zalo.me/s/public-article"}).encode(),
    ])
    lineage = SourceLineage(case_id="c", run_id="r", task_id="t",
        provider_id="coccoc_browser", provider_version="local-coccoc",
        parent_observable_value="alice", parent_observable_type=ObservableType.USERNAME)

    observations = CocCocBrowserAdapter().parse(raw, lineage)

    assert {obs.observable.type for obs in observations} == {ObservableType.ACCOUNT, ObservableType.URL}
    assert sum(obs.observable.type == ObservableType.ACCOUNT for obs in observations) == 1
    assert all(obs.raw_data["match_basis"] == "coccoc_search_candidate" for obs in observations)


@pytest.mark.asyncio
async def test_execute_reports_fixture_candidates_without_opening_browser(monkeypatch):
    adapter = CocCocBrowserAdapter()
    async def collect(_target, _options):
        return [{"source": "GitHub", "state": "CANDIDATE",
                 "url": "https://github.com/alice"}], None
    monkeypatch.setattr(adapter, "_collect", collect)
    from spider.models.observable import NormalizedObservable
    target = NormalizedObservable(type=ObservableType.USERNAME, value="alice")
    lineage = SourceLineage(case_id="c", run_id="r", task_id="t",
        provider_id="coccoc_browser", provider_version="local-coccoc",
        parent_observable_value="alice", parent_observable_type=ObservableType.USERNAME)
    result = await adapter.execute(target, lineage)
    assert result.outcome == "PARTIAL"  # One fixture row is not full source coverage.
    assert result.metadata["coverage"]["found"] == 1
    workflow = result.metadata["browser_workflow"]
    assert workflow["owned_tabs_max"] == 3 and workflow["owned_tabs_closed"]
    assert workflow["automatic_replay"] is False
    assert workflow["steps"][0]["content_sha256"]
    assert len(result.observations) == 2


@pytest.mark.asyncio
async def test_execute_reports_browser_network_failure_without_fake_site_coverage(monkeypatch):
    adapter = CocCocBrowserAdapter()

    async def collect(_target, _options):
        return [], "BROWSER_NETWORK_UNAVAILABLE"

    monkeypatch.setattr(adapter, "_collect", collect)
    from spider.models.observable import NormalizedObservable
    target = NormalizedObservable(type=ObservableType.USERNAME, value="public-handle")
    lineage = SourceLineage(case_id="c", run_id="r", task_id="t",
        provider_id="coccoc_browser", provider_version="local-coccoc",
        parent_observable_value="public-handle", parent_observable_type=ObservableType.USERNAME)

    result = await adapter.execute(target, lineage)

    assert result.outcome == "FAILED"
    assert result.metadata["coverage"]["checked"] == 0
    assert result.metadata["coverage"]["unprocessed"] == 11
    assert "Không kết luận về username" in result.error_message
