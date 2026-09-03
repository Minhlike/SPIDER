import json
import re

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def investigate(page, base_url, target, target_type="DOMAIN", final_status="COMPLETED"):
    events = []
    page.on("websocket", lambda ws: ws.on("framereceived", lambda frame: events.append(json.loads(frame))))
    page.goto(base_url)
    expect(page.locator("html")).to_have_attribute("lang", "vi")
    expect(page.locator("body")).not_to_have_class(re.compile("dark-theme"))
    expect(page.locator("#nav-investigate")).to_contain_text("Cuộc điều tra mới")
    page.locator("#nav-investigate").click()
    page.locator("#target-input").fill(target)
    page.locator("#target-type-select").select_option(target_type)
    expect(page.locator("#type-preview")).to_have_text(target_type)
    with page.expect_response(lambda response: response.url.endswith("/api/investigate") and response.request.method == "POST") as response:
        page.locator("#btn-start-investigate").click()
    queued = response.value.json()
    assert queued["status"] == "QUEUED" and queued["run_id"]
    expect(page.locator("#case-tab-content-live")).to_be_visible()
    expect(page.locator("#live-run-status")).to_have_text("RUNNING", timeout=5000)
    expect(page.locator("#case-status-badge")).to_have_text(final_status, timeout=15000)
    assert any(event["event"] == "RUN_COMPLETED" for event in events)
    insights = page.request.get(f"{base_url}/api/cases/{queued['case_id']}/insights").json()
    assert insights["run_id"] == queued["run_id"]
    return queued


def test_critical_investigation_flow(browser_app):
    page, base_url, errors = browser_app
    queued = investigate(page, base_url, "example.com")
    page.locator("#tab-btn-summary").click()
    expect(page.locator("#sum-kpi-entities")).to_have_text("2")
    expect(page.locator("#sum-kpi-sources")).to_have_text(re.compile(r"[1-9]\d*"))
    expect(page.locator("#case-meta")).to_contain_text("example.com")
    expect(page.locator("#empty-reason-container")).not_to_be_visible()
    page.locator("#tab-btn-sources").click()
    expect(page.locator("#sources-tbody tr").filter(has_text="native_dns")).to_contain_text("SUCCESS")
    page.locator("#tab-btn-evidence").click()
    evidence = page.locator("#evidence-tbody tr").filter(has_text="192.0.2.10")
    expect(evidence).to_contain_text("dns_a")
    evidence.get_by_role("button").click()
    expect(page.locator("#drawer-content")).to_contain_text("192.0.2.10")
    page.locator("#side-drawer .drawer-close").click()
    page.locator("#tab-btn-graph").click()
    expect(page.locator("#graph-node-count-badge")).to_have_text("2 thực thể, 1 liên kết")
    expect(page.locator("#cy-container canvas").first).to_be_visible()
    # Assert actual rendered graph model, then use a genuine browser click on the node.
    page.wait_for_function("cyInstance && cyInstance.nodes().length === 2 && cyInstance.edges().length === 1")
    pos = page.evaluate("cyInstance.nodes().filter(n => n.data('label') === '192.0.2.10')[0].renderedPosition()")
    page.locator("#cy-container").click(position=pos)
    expect(page.locator("#drawer-content")).to_contain_text("dns_a")
    expect(page.locator("#drawer-content")).to_contain_text("Task ID")
    assert not errors


def test_empty_result_explains_executed_and_missing_sources(browser_app):
    page, base_url, errors = browser_app
    investigate(page, base_url, "empty.example")
    page.locator("#tab-btn-summary").click()
    banner = page.locator("#empty-reason-container")
    expect(banner).to_be_visible()
    expect(banner).to_contain_text("Không tìm thấy thông tin bổ sung")
    expect(banner).to_contain_text("native_dns")
    expect(banner).to_contain_text("uncover")
    assert not errors


def test_username_real_worker_profile_sources_evidence_graph(browser_app):
    page, base_url, errors = browser_app
    queued = investigate(page, base_url, "fixture-user", "USERNAME")
    page.locator("#tab-btn-summary").click()
    card = page.locator("#public-profile-card")
    expect(card).to_contain_text("Synthetic Profile")
    expect(card).to_contain_text("Fixture Public Name")
    expect(card).to_contain_text("Trùng username")
    expect(card.locator("script")).to_have_count(0)
    page.locator("#tab-btn-sources").click()
    source = page.locator("#sources-tbody tr").filter(has_text="maigret")
    expect(source).to_contain_text("SUCCESS")
    expect(source).to_contain_text("3/3 website")
    page.locator("#tab-btn-evidence").click()
    expect(page.locator("#evidence-tbody")).to_contain_text("maigret_present")
    page.locator("#tab-btn-graph").click()
    page.wait_for_function("cyInstance && cyInstance.nodes().length >= 5 && cyInstance.edges().length >= 4")
    assert not errors


def test_email_public_match_is_separate_from_mail_infrastructure(browser_app):
    page, base_url, errors = browser_app
    queued = investigate(page, base_url, "owner@example.org", "EMAIL")
    page.locator("#tab-btn-summary").click()
    expect(page.locator("#public-profile-card")).to_contain_text("Email công khai trùng khớp")
    expect(page.locator("#public-profile-card")).to_contain_text("Synthetic Profile")
    expect(page.locator("#type-specific-container")).to_contain_text("Hạ tầng Email")
    insights = page.request.get(f"{base_url}/api/cases/{queued['case_id']}/insights").json()
    assert insights["profile_evidence"]["exact_email_matches"] == 1
    assert insights["profile_evidence"]["identity_verified"] is False
    assert not errors


@pytest.mark.parametrize("username_sites", [["Present", "Blocked"]], indirect=True)
def test_partial_source_stays_partial_in_browser(browser_app):
    page, base_url, errors = browser_app
    investigate(page, base_url, "fixture-user", "USERNAME", "PARTIAL")
    page.locator("#tab-btn-sources").click()
    source = page.locator("#sources-tbody tr").filter(has_text="maigret")
    expect(source).to_contain_text("PARTIAL")
    expect(source).to_contain_text("1 chưa xác định")
    assert not errors


def test_email_infrastructure_does_not_hide_missing_profile(browser_app):
    page, base_url, errors = browser_app
    investigate(page, base_url, "empty-profile@example.org", "EMAIL")
    page.locator("#tab-btn-summary").click()
    expect(page.locator("#sum-kpi-entities")).to_have_text("2")
    expect(page.locator("#public-profile-card")).to_contain_text("Chưa có hồ sơ công khai")
    expect(page.locator("#public-profile-card")).to_contain_text("github_public")
    assert not errors
