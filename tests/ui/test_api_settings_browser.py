"""Real Chromium, in-process API, synthetic keys and mocked provider results."""
import pytest
from playwright.sync_api import expect
from test_target_input_browser import offline_page

from spider.providers.uncover import api_access as access
from spider.web.api import settings


def open_modal(page):
    page.evaluate("openSettingsModal()")
    expect(page.locator("#settings-modal")).to_have_class("modal-overlay open")
    expect(page.locator("#key-state-censys")).to_contain_text("Thiếu trường")


@pytest.mark.parametrize("engine,state", [("shodan","VALID"), ("censys","INVALID_CREDENTIAL"), ("fofa","PLAN/QUOTA_LIMIT")])
def test_save_test_and_delete_show_real_state(offline_page, monkeypatch, engine, state):
    page, _, errors = offline_page
    calls = []
    async def check(actual, keys):
        calls.append(actual)
        assert all(keys.get(field) for field in access.REQUIREMENTS[actual])
        return access.result_state(actual, state, "REQUEST_ACCEPTED")
    monkeypatch.setattr(access, "run_engine", check)
    open_modal(page)
    names = {"SHODAN_API_KEY":"setting-key-shodan", "CENSYS_API_TOKEN":"setting-key-censys",
             "CENSYS_ORGANIZATION_ID":"setting-censys-org", "FOFA_EMAIL":"setting-fofa-email", "FOFA_KEY":"setting-key-fofa"}
    for field in access.REQUIREMENTS[engine]:
        page.locator("#" + names[field]).fill("synthetic-browser-" + field.lower())
    page.locator(f'[data-api-engine="{engine}"] [data-key-test]').click()
    expect(page.locator(f"#key-state-{engine}")).to_contain_text(state)
    if state == "VALID":
        expect(page.locator(f"#key-state-{engine}")).to_contain_text("Chưa kiểm thử quyền tìm kiếm")
    assert calls == [engine]
    for field in access.REQUIREMENTS[engine]:
        expect(page.locator("#" + names[field])).to_have_value("")
    assert "synthetic-browser" not in page.evaluate("JSON.stringify(localStorage)")
    assert "synthetic-browser" not in settings.SETTINGS_FILE.read_text()
    assert "synthetic-browser" not in page.locator("body").inner_text()
    page.locator(f'[data-api-engine="{engine}"] [data-key-delete]').click()
    expect(page.locator(f"#key-state-{engine}")).to_contain_text("Thiếu trường")
    assert not errors


def test_free_censys_token_and_network_error_are_not_success(offline_page, monkeypatch):
    page, _, errors = offline_page
    async def check(engine, keys):
        return access.result_state(engine, "NETWORK_ERROR", "TIMEOUT")
    monkeypatch.setattr(access, "run_engine", check)
    open_modal(page)
    page.locator("#setting-key-censys").fill("synthetic-pat")
    page.locator('[data-api-engine="censys"] [data-key-test]').click()
    expect(page.locator("#key-state-censys")).to_contain_text("NETWORK_ERROR")
    page.locator("#setting-censys-org").fill("synthetic-org")
    page.locator('[data-api-engine="censys"] [data-key-test]').click()
    expect(page.locator("#key-state-censys")).to_contain_text("NETWORK_ERROR")
    assert not errors


def test_save_failure_and_cancel_clear_passwords(offline_page):
    page, _, errors = offline_page
    open_modal(page)
    page.locator("#setting-key-shodan").fill("synthetic-unsaved")
    page.evaluate("closeSettingsModal()")
    expect(page.locator("#setting-key-shodan")).to_have_value("")
    open_modal(page)
    page.route("**/api/settings", lambda route: route.fulfill(status=503, json={"detail":"unavailable"}) if route.request.method == "POST" else route.fallback())
    page.locator("#setting-key-shodan").fill("synthetic-failed-save")
    page.locator('[data-api-engine="shodan"] [data-key-test]').click()
    expect(page.locator("#key-state-shodan")).to_contain_text("Chưa xác minh thành công")
    expect(page.locator("#setting-key-shodan")).to_have_value("")
    assert not errors


def test_whatismyip_key_save_test_and_delete(offline_page, monkeypatch):
    from spider.providers.whatismyip import adapter
    page, _, errors = offline_page
    async def check(key):
        assert key == "synthetic-browser-whatismyip"
        return {"engine": "whatismyip", "state": "VALID", "reason": "REQUEST_ACCEPTED",
                "scope": "account", "cached": False}
    monkeypatch.setattr(adapter, "check_api_key", check)
    open_modal(page)
    page.locator("#setting-key-whatismyip").fill("synthetic-browser-whatismyip")
    page.locator('[data-api-engine="whatismyip"] [data-key-test]').click()
    expect(page.locator("#key-state-whatismyip")).to_contain_text("VALID")
    expect(page.locator("#setting-key-whatismyip")).to_have_value("")
    assert "synthetic-browser-whatismyip" not in page.locator("body").inner_text()
    assert "synthetic-browser-whatismyip" not in settings.SETTINGS_FILE.read_text()
    page.locator('[data-api-engine="whatismyip"] [data-key-delete]').click()
    expect(page.locator("#key-state-whatismyip")).to_contain_text("Thiếu trường")
    assert not errors
