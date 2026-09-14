import asyncio

import pytest

from spider.providers.browser.challenges import BrowserChallengeRegistry, browser_challenges
from spider.providers.browser.coccoc import CocCocBrowserAdapter
from spider.models.enums import ObservableType
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage


@pytest.mark.asyncio
async def test_registry_exposes_only_safe_operational_metadata_and_continues_run():
    registry = BrowserChallengeRegistry()
    waiting = asyncio.create_task(registry.wait("run-1", "Cốc Cốc Search", 1))
    for _ in range(20):
        items = registry.list_for_run("run-1")
        if items:
            break
        await asyncio.sleep(0)

    assert len(items) == 1
    assert set(items[0]) == {"challenge_id", "source", "state", "created_at", "expires_at"}
    assert registry.continue_run("run-1") == 1
    assert await waiting == "CONTINUE"
    assert registry.list_for_run("run-1") == []


@pytest.mark.asyncio
async def test_registry_timeout_removes_pending_item():
    registry = BrowserChallengeRegistry()
    assert await registry.wait("run-timeout", "Instagram", 0.01) == "TIMEOUT"
    assert registry.list_for_run("run-timeout") == []


@pytest.mark.asyncio
async def test_browser_challenge_keeps_page_then_reloads_exact_step(monkeypatch):
    adapter = CocCocBrowserAdapter()

    class Response:
        status = 200

    class Locator:
        async def inner_text(self, **_kwargs):
            return "Public result after confirmation"

    class Page:
        url = "https://coccoc.com/search"
        reloads = 0

        async def reload(self, **_kwargs):
            self.reloads += 1
            return Response()

        async def wait_for_timeout(self, _milliseconds):
            return None

        def locator(self, _selector):
            return Locator()

    page = Page()

    async def collect(_target, _options):
        status, unresolved = await adapter._resolve_human_challenge(
            page, "Cốc Cốc Search", 403, "Security check - captcha", 1000)
        assert status == 200 and unresolved is False
        return [], None

    monkeypatch.setattr(adapter, "_collect", collect)
    lineage = SourceLineage(case_id="case", run_id="run-browser", task_id="task",
        provider_id="coccoc_browser", provider_version="local-coccoc",
        parent_observable_value="fixture-user", parent_observable_type=ObservableType.USERNAME)
    task = asyncio.create_task(adapter.execute(
        NormalizedObservable(type=ObservableType.USERNAME, value="fixture-user"),
        lineage, timeout_seconds=30))
    for _ in range(100):
        if browser_challenges.list_for_run("run-browser"):
            break
        await asyncio.sleep(0)
    assert browser_challenges.continue_run("run-browser") == 1
    await task
    assert page.reloads == 1
