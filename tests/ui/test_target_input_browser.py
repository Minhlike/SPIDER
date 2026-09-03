"""Real Chromium + in-process API: no listening SPIDER server or live providers."""
import json
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
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(__file__).resolve().parents[2] / "runtime/playwright"))
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


def test_dotted_username_and_explicit_marker(offline_page):
    page, dispatches, errors = offline_page
    page.locator("#target-input").fill("ms.orianawren")
    expect(page.locator("#type-preview")).to_have_text("USERNAME")
    expect(page.locator("#classification-explanation")).to_contain_text("dấu chấm")
    page.locator("#target-input").fill("@Mixed.Case")
    expect(page.locator("#type-preview")).to_have_text("USERNAME")
    with page.expect_response("**/api/investigate") as queued:
        page.locator("#btn-start-investigate").click()
    assert queued.value.json()["type"] == "USERNAME"
    assert dispatches[0]["target"] == "@Mixed.Case"
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
