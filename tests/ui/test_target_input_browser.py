"""Real Chromium + in-process API: no listening SPIDER server or live providers."""
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect

from spider.models.classifier import TargetClassifier
from spider.service.service import SpiderService


@pytest.fixture
def offline_page(tmp_path, monkeypatch):
    import spider.web.app as web_app
    service = SpiderService(db_path=str(tmp_path / "browser.db"), artifacts_dir=str(tmp_path / "runs"))
    monkeypatch.setattr(web_app, "create_spider_service", lambda **kwargs: service)
    monkeypatch.setattr(web_app, "source_preflight", lambda _service, observable_type, _mode=None,
                        _browser=False: {
        "investigation_mode": ("PERSONAL_FOOTPRINT" if observable_type.value in ("USERNAME", "EMAIL")
                               else "INFRASTRUCTURE"),
        "sources": ([{"provider_id": "maigret", "capability": "USERNAME_DISCOVERY",
                      "network_class": "THIRD_PARTY_ONLY", "request_accounting": "SUPPORTED",
                      "credential_scope": "NOT_REQUIRED"}]
                    if observable_type.value == "USERNAME" else []),
        "internet_api_keys_applicable": False,
    })
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(__file__).resolve().parents[2] / "runtime/playwright"))
    previous_policy = asyncio.get_event_loop_policy()
    if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        with TestClient(web_app.create_app()) as client, sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            dispatches, errors = [], []

            def serve(route):
                request = route.request
                url = urlsplit(request.url)
                if url.hostname != "spider.test":
                    route.abort()
                    return
                if url.path == "/api/investigate":
                    dispatches.append(request.post_data_json)
                response = client.request(request.method, url.path + ("?" + url.query if url.query else ""),
                                          content=request.post_data, headers={"Content-Type": "application/json"})
                route.fulfill(status=response.status_code, body=response.content,
                              content_type=response.headers.get("content-type", "application/json"))

            page.route("**/*", serve)
            page.route_web_socket("**/ws", lambda socket: None)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto("http://spider.test/")
            expect(page.locator("html")).to_have_attribute("lang", "vi")
            page.locator("#nav-investigate").click()
            try:
                yield page, dispatches, errors
            finally:
                browser.close()
    finally:
        asyncio.set_event_loop_policy(previous_policy)


def test_dotted_username_and_explicit_marker(offline_page):
    page, dispatches, errors = offline_page
    page.locator("#target-input").fill("ms.orianawren")
    expect(page.locator("#type-preview")).to_have_text("USERNAME")
    expect(page.locator("#classification-explanation")).to_contain_text("dấu chấm")
    expect(page.locator("#source-preflight")).to_contain_text("maigret")
    expect(page.locator("#source-preflight")).to_contain_text("Shodan/Censys/FOFA không áp dụng")
    page.locator("#target-input").fill("@Mixed.Case")
    expect(page.locator("#type-preview")).to_have_text("USERNAME")
    with page.expect_response("**/api/investigate") as queued:
        page.locator("#btn-start-investigate").click()
    assert queued.value.json()["type"] == "USERNAME"
    assert dispatches[0]["target"] == "@Mixed.Case"
    assert dispatches[0]["investigation_mode"] == "AUTO"
    assert dispatches[0]["browser_assisted"] is True
    assert dispatches[0]["budget"]["username_source_scope"] == "VN_COMMON_CORE"
    assert not errors


def test_passive_button_does_not_request_signed_in_coccoc(offline_page):
    page, dispatches, errors = offline_page
    page.locator("#target-input").fill("fixture-user")
    with page.expect_response("**/api/investigate"):
        page.locator("#btn-browser-investigate").click()
    assert dispatches[0]["browser_assisted"] is False
    assert dispatches[0]["budget"]["max_requests"] == 100
    assert not errors


def test_browser_button_is_hidden_for_infrastructure_target(offline_page):
    page, _, errors = offline_page
    page.locator("#target-input").fill("example.com")
    expect(page.locator("#type-preview")).to_have_text("DOMAIN")
    expect(page.locator("#btn-browser-investigate")).to_be_hidden()
    assert not errors


def test_selecting_ip_autofills_current_public_address_without_starting(offline_page, monkeypatch):
    from spider.web.api import network
    page, dispatches, errors = offline_page
    async def current(version):
        assert version == 4
        return {"ip": "8.8.8.8", "version": 4, "source": "whatismyip_api",
                "observed_at": "2026-09-05T00:00:00+00:00", "cached": False}
    monkeypatch.setattr(network, "resolve_public_address", current)
    with page.expect_response("**/api/network/public-address?version=4") as response_info:
        page.locator("#target-type-select").select_option("IP_ADDRESS")
    assert response_info.value.status == 200, response_info.value.text()
    expect(page.locator("#target-input")).to_have_value("8.8.8.8")
    expect(page.locator("#public-ip-status")).to_contain_text("WhatIsMyIP")
    expect(page.locator("#type-preview")).to_have_text("IP_ADDRESS")
    assert dispatches == []
    assert not errors


def test_ip_report_renders_enrichment_and_source_provenance(offline_page):
    page, _, errors = offline_page
    page.evaluate("""() => renderTypeSpecificInsights({
      target_type: 'IP_ADDRESS', entities_count: 3,
      ip_insights: {
        ip: '8.8.8.8', asn: 'AS15169', cidr: '8.8.8.0/24',
        organization: 'Fixture Network', isp: 'Fixture ISP', rir: 'ARIN',
        network_name: 'FIXTURE-NET', country: 'United States', region: 'California',
        city: 'Mountain View', postal_code: '94035', latitude: 37.4,
        longitude: -122.1, time_zone: 'America/Los_Angeles',
        is_proxy: false, is_vpn: null, is_datacenter: null,
        proxy_type: null, proxy_type_description: 'No proxy detected',
        proxy_range: null, associated_hostnames: ['dns.fixture.invalid'], contacts: [],
        source_observations: [{provider_id: 'whatismyip',
          record_kind: 'whatismyip_ip_intelligence',
          observed_at: '2026-09-05T00:00:00+00:00', confidence: 0.72}]
      }
    })""")
    report = page.locator("#type-specific-container")
    expect(report).to_contain_text("Hồ sơ tình báo địa chỉ IP")
    expect(report).to_contain_text("AS15169")
    expect(report).to_contain_text("No proxy detected")
    expect(report).to_contain_text("whatismyip")
    expect(report).to_contain_text("không xác định cá nhân hoặc địa chỉ nhà")
    assert not errors


@pytest.mark.parametrize("choice", ["USERNAME", "DOMAIN"])
def test_ambiguous_input_requires_choice_before_dispatch(offline_page, choice):
    page, dispatches, errors = offline_page
    page.locator("#target-input").fill("alice.dev")
    expect(page.locator("#classification-explanation")).to_contain_text("Hãy chọn loại")
    page.locator("#btn-start-investigate").click()
    expect(page.locator("#target-type-select")).to_be_focused()
    assert not dispatches
    page.locator("#target-type-select").select_option(choice)
    with page.expect_response("**/api/investigate") as queued:
        page.locator("#btn-start-investigate").click()
    assert queued.value.json()["type"] == choice
    assert dispatches[0]["target_type"] == choice
    assert not errors


def test_changed_input_resets_override_and_old_response_cannot_overwrite(offline_page):
    page, _, errors = offline_page
    page.locator("#target-input").fill("alice.dev")
    page.locator("#target-type-select").select_option("DOMAIN")
    expect(page.locator("#classification-explanation")).to_contain_text("đã chỉ định")
    # Simulate an uncancellable old request. The sequence guard must still work.
    old = TargetClassifier.classify("alice.dev").model_dump(mode="json")
    old["type"] = old["detected_type"]
    page.evaluate("""old => {
      const original = window.fetch;
      window.fetch = (url, options) => {
        if (url === '/api/classify' && JSON.parse(options.body).target === 'alice.dev') {
          return new Promise(resolve => { window.releaseOldClassification = () => resolve(new Response(JSON.stringify(old))); });
        }
        return original(url, options);
      };
      onTargetInputDebounced();
    }""", old)
    page.wait_for_function("typeof window.releaseOldClassification === 'function'")
    page.locator("#target-input").fill("ms.orianawren")
    expect(page.locator("#target-type-select")).to_have_value("")
    expect(page.locator("#type-preview")).to_have_text("USERNAME")
    page.evaluate("window.releaseOldClassification()")
    expect(page.locator("#type-preview")).to_have_text("USERNAME")
    assert not errors


def test_research_controls_light_default_and_empty_result_explanation(offline_page):
    page, _, errors = offline_page
    expect(page.locator("body")).not_to_have_class("dark-theme")
    expect(page.locator("#theme-label")).to_have_text("Sáng")
    assert page.locator("#insight-target").count() == 1
    assert page.locator("#insight-question option").all_text_contents() == [
        "Tất cả bằng chứng / All evidence",
        "Hồ sơ công khai / Public profiles",
        "Hạ tầng / Infrastructure",
    ]

    page.locator("#target-input").fill("synthetic-empty-user")
    with page.expect_response("**/api/investigate") as queued:
        page.locator("#btn-start-investigate").click()
    case_id = queued.value.json()["case_id"]
    page.wait_for_function("""async caseId => {
      const response = await fetch(`/api/cases/${caseId}/insights`);
      const data = await response.json();
      return data.status === 'COMPLETED';
    }""", arg=case_id)
    page.evaluate("""async caseId => {
      switchCaseTab('summary');
      await loadCaseDetail(caseId);
    }""", case_id)
    expect(page.locator("#empty-reason-container")).to_be_visible()
    expect(page.locator("#empty-reason-container")).to_contain_text(
        "Không tìm thấy thông tin bổ sung cho mục tiêu này")
    expect(page.locator("#scope-explanation")).to_contain_text("Bằng chứng chưa xác định mục tiêu bị loại")
    expect(page.locator("#evidence-bundle-download")).to_have_attribute("href", re.compile(re.escape(case_id)))
    page.evaluate("""async () => {
      switchCaseTab('sources');
      await loadCaseSources();
    }""")
    expect(page.locator("#sources-tbody")).to_contain_text("Không áp dụng cho loại mục tiêu này")
    expect(page.locator("#sources-tbody")).not_to_contain_text("Chưa cấu hình API Key tìm kiếm")
    diagnostic = page.evaluate("""coverageDescription({coverage: {
      selected: 3, checked: 3, found: 0, not_found: 0, unknown: 3, invalid: 0,
      unprocessed: 0, non_unique_detections: 0, controls_pending: 0, controls_unknown: 0,
      priority_sites: {
        Instagram: {outcome: 'UNKNOWN', reason: 'LOGIN_REQUIRED'},
        Threads: {outcome: 'UNKNOWN', reason: 'PARSER_DRIFT'},
        TikTok: {outcome: 'UNKNOWN', reason: 'BLOCKED'}
      }
    }})""")
    assert "Instagram: cần đăng nhập" in diagnostic
    assert "Threads: chưa xác định — rule đã lệch" in diagnostic
    assert "TikTok: bị chặn/challenge" in diagnostic
    assert not errors
