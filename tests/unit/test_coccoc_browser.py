import asyncio
import json

import pytest

from spider.models.enums import ObservableType
from spider.models.provenance import SourceLineage
from spider.providers.browser.coccoc import (
    CocCocBrowserAdapter, apply_negative_control, classify_direct_candidate, classify_direct_result,
    browser_start_reason, coccoc_profile, host_matches,
    safe_result_url,
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
        "https://www.threads.com/@alice", "Threads", "Profile shell",
        ["https://www.threads.com/@alice"])[0] == "CANDIDATE"
    assert classify_direct_result("tiktok.com", "alice", 429,
        "https://www.tiktok.com/@alice", "TikTok", "Too many requests")[0] == "RATE_LIMITED"
    assert classify_direct_result("tiktok.com", "alice", 403,
        "https://www.tiktok.com/@alice", "Security check", "captcha")[0] == "BLOCKED"


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
    assert len(result.observations) == 2
