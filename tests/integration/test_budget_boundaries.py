import asyncio
import pytest
import httpx
import dns.message
import dns.rrset
import dns.flags
from sqlalchemy import select
from spider.models.budget import BudgetLedger, ExecutionBudget, RequestBudgetExceeded
from spider.models.enums import ObservableType as T
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage
from spider.providers.transport import MeteredTransport
from spider.providers.http_plane import HTTPPlane
from spider.providers.native.dns import NativeDnsAdapter
from spider.providers.fake.provider_a import FakeProviderA
from spider.service.service import SpiderService
from spider.storage.schema import ObservationRecord, ProviderRunRecord


class _Recorder:
    def __init__(self):
        self.events = []

    async def begin(self, destination, purpose, credentialed, identifier):
        self.events.append({"destination": destination, "purpose": purpose,
                            "credentialed": credentialed, "identifier": identifier})
        return "event"

    async def finish(self, event, outcome):
        self.events[-1]["outcome"] = outcome


@pytest.mark.asyncio
async def test_api_key_header_is_credentialed_and_never_enters_replay_cache():
    recorder, plane = _Recorder(), HTTPPlane()
    transport = MeteredTransport(
        BudgetLedger(), ExecutionBudget(max_requests=2), "fixture",
        httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True})),
        recorder=recorder, plane=plane, run_scope=("run", "v1"),
    )
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get(
            "https://credentialed.example.invalid/account",
            headers={"X-API-KEY": "synthetic-secret"},
            extensions={"spider_purpose": "credential_check"},
        )
    assert response.status_code == 200
    assert recorder.events[0]["credentialed"] is True
    assert recorder.events[0]["outcome"] == "HTTP_200"
    assert not plane.cache
    await plane.aclose()


@pytest.mark.asyncio
async def test_redirect_retry_and_control_share_hard_transport_budget():
    requests = []
    def upstream(request):
        requests.append(request.url.path)
        if request.url.path == "/redirect":
            return httpx.Response(302, headers={"location": "/landing"})
        if request.url.path == "/retry" and requests.count("/retry") == 1:
            raise httpx.ConnectError("Synthetic network failure")
        return httpx.Response(200)
    ledger, budget = BudgetLedger(), ExecutionBudget(max_requests=5)
    transport = MeteredTransport(ledger, budget, "fixture", httpx.MockTransport(upstream))
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        await client.get("https://fixture.test/redirect")
        with pytest.raises(httpx.ConnectError):
            await client.get("https://fixture.test/retry")
        await client.get("https://fixture.test/retry")
        await client.get("https://fixture.test/control")
        with pytest.raises(RequestBudgetExceeded):
            await client.get("https://fixture.test/blocked")
    assert requests == ["/redirect", "/landing", "/retry", "/retry", "/control"]
    assert ledger.requests_count == 5 and len(ledger.request_events) == 5
    assert "fixture.test" not in ledger.model_dump_json()


@pytest.mark.asyncio
async def test_concurrent_http_requests_cannot_overspend():
    ledger, budget = BudgetLedger(), ExecutionBudget(max_requests=3)
    seen = []
    def upstream(request):
        seen.append(1)
        return httpx.Response(200)
    async with httpx.AsyncClient(transport=MeteredTransport(ledger, budget, "fixture", httpx.MockTransport(upstream))) as client:
        results = await asyncio.gather(*(client.get("https://fixture.test/") for _ in range(10)), return_exceptions=True)
    assert len(seen) == ledger.requests_count == 3
    assert sum(isinstance(r, RequestBudgetExceeded) for r in results) == 7


@pytest.mark.asyncio
async def test_explicit_replay_cache_does_not_consume_network_budget():
    ledger, budget, dispatched = BudgetLedger(), ExecutionBudget(max_requests=1), []
    plane = HTTPPlane()
    def upstream(request):
        dispatched.append(request.url.path)
        return httpx.Response(200, json={"fixture": True})
    async with httpx.AsyncClient(transport=MeteredTransport(ledger, budget, "fixture",
            httpx.MockTransport(upstream), plane=plane, run_scope=("run", "v1"))) as client:
        first = await client.get("https://fixture.test/replay")
        second = await client.get("https://fixture.test/replay")
    assert first.json() == second.json() and len(dispatched) == 1
    assert ledger.requests_count == 1 and ledger.cache_hits_count == 1
    await plane.aclose()


@pytest.mark.asyncio
async def test_dns_tcp_fallback_counted_and_stops_at_limit(monkeypatch):
    calls = []
    async def udp(query, address, **kwargs):
        calls.append("UDP")
        response = dns.message.make_response(query)
        response.flags |= dns.flags.TC
        return response
    async def tcp(query, address, **kwargs):
        calls.append("TCP")
        response = dns.message.make_response(query)
        response.answer.append(dns.rrset.from_text("example.test", 60, "IN", "A", "192.0.2.1"))
        return response
    monkeypatch.setattr("dns.asyncquery.udp", udp)
    monkeypatch.setattr("dns.asyncquery.tcp", tcp)
    ledger, budget = BudgetLedger(), ExecutionBudget(max_requests=2)
    target = NormalizedObservable(type=T.DOMAIN, value="example.test")
    lineage = SourceLineage(case_id="case", run_id="run", task_id="task", provider_id="native_dns", provider_version="1")
    result = await NativeDnsAdapter().execute(target, lineage, request_ledger=ledger, execution_budget=budget)
    assert calls == ["UDP", "TCP"] and ledger.requests_count == 2
    assert len(result.observations) == 1 and result.outcome == "PARTIAL"


@pytest.mark.asyncio
async def test_entity_ingest_cap_persists_and_rebuild_cannot_bypass(tmp_path):
    service = SpiderService(db_path=str(tmp_path / "budget.db"), artifacts_dir=str(tmp_path / "runs"))
    service.provider_manager.register_adapter(FakeProviderA())
    service.capability_registry.get_capability("SUBDOMAIN_DISCOVERY").default_providers = ["fake_a"]
    await service.start()
    try:
        case = await service.create_case("Synthetic budget case")
        await service.add_target(case["id"], "example.test", T.DOMAIN)
        run = await service.investigate(case["id"], budget=ExecutionBudget(max_entities=3))
        assert run["status"] == "PARTIAL" and run["entities_count"] == 3
        assert run["budget_ledger"]["entities_count"] == 3
        assert run["budget_ledger"]["requests_count"] == 0  # Fake provider uses no network.
        async with service.db_manager.session_factory() as session:
            assert len((await session.execute(select(ObservationRecord))).scalars().all()) == 3
            saved = await session.get(ProviderRunRecord, run["run_id"])
            assert saved.metadata_json["budget_ledger"] == run["budget_ledger"]
        rebuilt = await service.rebuild_case(case["id"])
        assert rebuilt["entities_rebuilt"] == 3
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_unmetered_provider_cannot_dispatch(tmp_path):
    class Opaque(FakeProviderA):
        request_budget_supported = False
        async def execute(self, *args, **kwargs):
            pytest.fail("Opaque provider must not dispatch with an unenforceable hard budget")
    service = SpiderService(db_path=str(tmp_path / "opaque.db"), artifacts_dir=str(tmp_path / "runs"))
    service.provider_manager.register_adapter(Opaque())
    service.capability_registry.get_capability("SUBDOMAIN_DISCOVERY").default_providers = ["fake_a"]
    await service.start()
    try:
        case = await service.create_case("Opaque fixture")
        await service.add_target(case["id"], "example.test", T.DOMAIN)
        run = await service.investigate(case["id"])
        assert run["status"] == "PARTIAL" and run["observations_collected"] == 0
    finally:
        await service.stop()
