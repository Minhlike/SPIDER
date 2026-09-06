import asyncio
import gzip
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import httpx
import pytest

from spider.models.budget import BudgetLedger, ExecutionBudget
from spider.providers.http_plane import HTTPPlane
from spider.providers.transport import provider_client


@pytest.mark.asyncio
async def test_anonymous_run_replay_coalesces_and_preserves_decoded_body():
    calls, now = [], [0]
    async def upstream(request):
        calls.append(request.url.path)
        await asyncio.sleep(.02)
        return httpx.Response(200, headers={"content-encoding": "gzip", "cache-control": "max-age=5"},
                              content=gzip.compress(b'{"ok":true}'))
    plane = HTTPPlane(factory=lambda: httpx.MockTransport(upstream), clock=lambda: now[0])
    ledger, budget = BudgetLedger(), ExecutionBudget(max_requests=10)
    async def get(task, scope="run-a", url="https://fixture.test/item"):
        async with provider_client("fixture", {"http_plane": plane, "http_run_scope": (scope, "v1"),
            "request_ledger": ledger.for_task(task), "execution_budget": budget}) as client:
            return (await client.get(url)).json()
    try:
        assert await asyncio.gather(get("a"), get("b")) == [{"ok": True}, {"ok": True}]
        assert len(calls) == ledger.requests_count == 1 and ledger.cache_hits_count == 1
        assert ledger.cache_count_for_task("a") + ledger.cache_count_for_task("b") == 1
        now[0] = 6
        await get("a")
        await get("a", scope="run-b")
        for _ in range(2):
            await get("a", url="https://fixture.test/item?api_key=synthetic")
        assert len(calls) == ledger.requests_count == 5
        assert not plane.locks
    finally:
        await plane.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [{"cache-control": "no-store"}, {"cache-control": "private"},
    {"cache-control": "no-cache"}, {"cache-control": "max-age=0"}, {"set-cookie": "fixture=1"}, {"vary": "*"}])
async def test_private_or_uncacheable_responses_are_not_replayed(headers):
    calls = []
    def upstream(request):
        calls.append(1)
        return httpx.Response(200, headers=headers, json={"ok": True})
    plane = HTTPPlane(factory=lambda: httpx.MockTransport(upstream))
    try:
        async with provider_client("fixture", {"http_plane": plane, "http_run_scope": ("run", "v1")}) as client:
            for _ in range(2):
                await client.get("https://fixture.test/item")
        assert len(calls) == 2 and not plane.cache
    finally:
        await plane.aclose()


@pytest.mark.asyncio
async def test_actual_connection_reuse_across_clients_and_credential_isolation():
    ports = []
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def log_message(self, *args):
            pass
        def do_GET(self):
            ports.append(self.client_address[1])
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"ok")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    plane = HTTPPlane()
    try:
        for key in (None, None, "synthetic-a", "synthetic-b", "synthetic-a"):
            async with provider_client("fixture", {"http_plane": plane, "http_run_scope": ("run", "v1")}) as client:
                result = await client.get(f"http://127.0.0.1:{server.server_port}/",
                    headers={"X-API-Key": key} if key else {})
                assert result.text == "ok"
        assert ports[0] == ports[1] and ports[2] == ports[4]
        assert len({ports[0], ports[2], ports[3]}) == 3
    finally:
        await plane.aclose()
        server.shutdown()
        server.server_close()
        thread.join(2)


@pytest.mark.asyncio
async def test_replay_memory_is_bounded_and_cancelled_leader_can_be_retried():
    entered, release = asyncio.Event(), asyncio.Event()
    async def upstream(request):
        if request.url.path == "/waiting":
            entered.set()
            await release.wait()
        return httpx.Response(200, content=b"ok")
    plane = HTTPPlane(factory=lambda: httpx.MockTransport(upstream))
    try:
        async with provider_client("fixture", {"http_plane": plane, "http_run_scope": ("run", "v1")}) as client:
            leader = asyncio.create_task(client.get("https://fixture.test/waiting"))
            await entered.wait()
            follower = asyncio.create_task(client.get("https://fixture.test/waiting"))
            leader.cancel()
            with pytest.raises(asyncio.CancelledError):
                await leader
            release.set()
            assert (await asyncio.wait_for(follower, 1)).text == "ok"
            for i in range(150):
                await client.get(f"https://fixture.test/{i}")
        assert len(plane.cache) == 128 and not plane.locks
    finally:
        await plane.aclose()
