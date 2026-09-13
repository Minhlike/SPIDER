"""Real browser/API/SQLite; only the external DNS execution boundary is fixed."""
import asyncio
import json
import os
from pathlib import Path
import socket
import threading
import time
from urllib.request import urlopen

import pytest
import uvicorn
import httpx
from playwright.sync_api import sync_playwright

from spider.models.enums import NetworkClass, ObservableType, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.providers.base import ProviderExecutionResult, ProviderHealth, BaseProviderAdapter
from spider.providers.native.dns import NativeDnsAdapter
from spider.service.service import SpiderService
from spider.providers.maigret.adapter import MaigretAdapter
from spider.providers.native.public_profiles import PublicProfilesAdapter
from benchmarks.public_sites import public_sites


class FixturePhoneBrowserAdapter(BaseProviderAdapter):
    """No-browser deterministic boundary for the real UI/API E2E contract."""
    request_budget_supported = True

    def provider_id(self): return "coccoc_browser"
    def version(self): return "fixture"
    def adapter_version(self): return "fixture"
    def capabilities(self): return ["BROWSER_PERSONAL_DISCOVERY"]
    def network_class(self): return NetworkClass.THIRD_PARTY_ONLY
    def accepts(self): return [ObservableType.PHONE]
    def produces(self): return [ObservableType.URL]
    async def health(self): return ProviderHealth(state=ProviderState.READY)
    def build_command(self, target): return []
    def normalize(self, raw_item): return NormalizedObservable.model_validate(raw_item)
    def parse(self, raw_content, lineage): return []

    async def execute(self, target, lineage, **_kwargs):
        url = "https://zalo.me/s/synthetic-public-mention"
        observation = Observation(
            observable=NormalizedObservable(type=ObservableType.URL, value=url),
            lineage=lineage.model_copy(update={"upstream_source": "fixture_browser",
                                               "upstream_family": "BROWSER_ASSISTED"}),
            confidence=0.55,
            raw_data={"phone_e164": target.canonical_value,
                      "evidence_class": "SEARCH_SNIPPET", "candidate_url": url,
                      "source_url": url, "identity_verified": False})
        return ProviderExecutionResult(
            raw_content=b"{}", observations=[observation], outcome="PARTIAL", exit_code=1,
            raw_items_count=1, accepted_count=1,
            metadata={"coverage": {"selected": 1, "checked": 1, "found": 0,
                "not_found": 0, "unknown": 1, "unprocessed": 0,
                "search_discovery": {"engine": "Fixture", "outcome": "COCCOC_SEARCH_RESULT",
                                     "candidate_profiles": 0, "unverified_leads": 1}}})


@pytest.fixture
def username_sites(tmp_path, request):
    with public_sites(tmp_path / "sites", getattr(request, "param", ["Present", "Absent", "SoftAbsent"])) as fixture:
        yield fixture


@pytest.fixture
def browser_app(tmp_path, monkeypatch, username_sites):
    # UI tests restore the event-loop policy that was active before their
    # Playwright fixture.  On Windows that can be Selector, which cannot start
    # Playwright's Node driver.  Keep this real-browser fixture independent of
    # collection order and restore the caller's policy after teardown.
    previous_policy = asyncio.get_event_loop_policy()
    if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    import spider.web.app as web_app
    service = SpiderService(db_path=str(tmp_path / "e2e.db"), artifacts_dir=str(tmp_path / "runs"))
    adapter = NativeDnsAdapter()

    async def fixed_dns(target, lineage, **kwargs):
        # A visible running phase without network timing dependencies.
        await asyncio.sleep(1)
        records = [{"type": "A", "value": "192.0.2.10"}] if target.canonical_value == "example.com" else []
        raw = json.dumps({"target": target.canonical_value,
                          "query_domain": target.canonical_value.rsplit("@", 1)[-1],
                          "records": records}).encode()
        return ProviderExecutionResult(raw_content=raw, observations=adapter.parse(raw, lineage),
                                       exit_code=0, mime_type="application/json")

    monkeypatch.setattr(adapter, "execute", fixed_dns)
    service.provider_manager.register_adapter(adapter)
    service.provider_manager.register_adapter(MaigretAdapter(database_path=username_sites["maigret"]))
    def public_profile(request):
        if request.url.path == "/search/users":
            if "empty-profile" in request.url.params["q"]:
                return httpx.Response(200, json={"items": [], "total_count": 0, "incomplete_results": False})
            return httpx.Response(200, json={"items": [{"login": "fixture-user"}], "total_count": 1,
                                             "incomplete_results": False})
        return httpx.Response(200, json={"login": "fixture-user", "email": "owner@example.org",
            "name": "Synthetic Profile", "bio": "Public biography <script>must not execute</script>"})
    service.provider_manager.register_adapter(PublicProfilesAdapter(httpx.MockTransport(public_profile)))
    service.provider_manager.register_adapter(FixturePhoneBrowserAdapter())
    monkeypatch.setattr(web_app, "create_spider_service", lambda **kwargs: service)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(web_app.create_app(), log_level="warning", access_log=False,
                                         timeout_graceful_shutdown=5))
    worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    worker.start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 15
        while not server.started and worker.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started, "E2E backend did not start"
        with urlopen(base_url + "/api/health", timeout=3) as response:
            assert json.load(response)["status"] == "HEALTHY"
        monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(__file__).resolve().parents[2] / "runtime/playwright"))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={"width": 1440, "height": 960})
            context.tracing.start(screenshots=True, snapshots=True)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                yield page, base_url, errors
            finally:
                # Synthetic data only; keep useful, ignored release QA artifacts.
                output = Path("test-results") / tmp_path.name
                output.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(output / "final.png"), full_page=True)
                context.tracing.stop(path=str(output / "trace.zip"))
                # Complete the WS close handshake before tearing down Chromium's
                # Windows sockets; abrupt reset can strand a Proactor transport.
                page.evaluate("if (socket) { socket.onclose = null; socket.close(1000); }")
                page.wait_for_function("!socket || socket.readyState === WebSocket.CLOSED", timeout=5000)
                context.close()
                browser.close()
    finally:
        server.should_exit = True
        worker.join(timeout=10)
        listener.close()
        try:
            assert not worker.is_alive(), "E2E backend did not stop cleanly"
        finally:
            asyncio.set_event_loop_policy(previous_policy)
