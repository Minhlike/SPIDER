"""Reproduce reliability gaps on synthetic data; no listener or external requests.

This is a diagnostic snapshot, not a passing security gate. Resolved findings
should change the observed values. Never opens the user's case database.
"""
import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from spider.core.factory import create_spider_service
from spider.models.budget import ExecutionBudget
from spider.models.entity import Entity
from spider.models.enums import ObservableType as T
from spider.providers.base import ProviderExecutionResult
from spider.providers.native.dns import NativeDnsAdapter
from spider.service.service import SpiderService
from spider.storage.repositories.graph_repo import GraphRepository


async def engine_findings(root):
    service = SpiderService(db_path=str(root / "engine.db"), artifacts_dir=str(root / "runs"))
    await service.start()
    try:
        case_id = (await service.create_case("Synthetic typed identity audit"))["id"]
        async def collide(session):
            first = await GraphRepository.upsert_entity(session, Entity(case_id=case_id, type=T.DOMAIN, canonical_name="alice.dev"))
            await session.flush()
            second = await GraphRepository.upsert_entity(session, Entity(case_id=case_id, type=T.USERNAME, canonical_name="alice.dev"))
            return {"same_entity_id": first.id == second.id, "second_record_type": second.observable_type}
        collision = await service.db_writer.submit(collide)

        adapter = NativeDnsAdapter()
        async def fixed_dns(target, lineage, **kwargs):
            raw = json.dumps({"target": target.canonical_value, "records": [
                {"type": "A", "value": f"192.0.2.{i}"} for i in range(1, 6)]}).encode()
            return ProviderExecutionResult(raw_content=raw, observations=adapter.parse(raw, lineage), exit_code=0)
        adapter.execute = fixed_dns
        service.provider_manager.register_adapter(adapter)
        budget_case = (await service.create_case("Synthetic entity budget audit"))["id"]
        await service.add_target(budget_case, "example.com", T.DOMAIN)
        result = await service.investigate(budget_case, budget=ExecutionBudget(max_depth=0, max_entities=1))
        budget_result = {"max_entities": 1, "saved_entities": len(await service.get_case_entities(budget_case)),
                        "status": result["status"], "external_requests": 0}
        return {"typed_identity": collision, "entity_budget": budget_result}
    finally:
        await service.stop()


async def unsupported_input(root):
    service = create_spider_service(db_path=str(root / "url.db"), artifacts_dir=str(root / "url-runs"))
    # Guard even against future scheduling changes. The audit never runs a provider.
    async def denied(*args, **kwargs):
        raise RuntimeError("External provider execution is forbidden in this diagnostic")
    service.provider_manager.execute_task = denied
    await service.start()
    try:
        case_id = (await service.create_case("Synthetic URL capability audit"))["id"]
        await service.add_target(case_id, "https://example.com/profile", T.URL)
        result = await service.investigate(case_id, budget=ExecutionBudget(max_depth=0))
        return {"registered_adapters": len(service.provider_manager.adapters),
                "url_capabilities": len(service.capability_registry.get_capabilities_for_input(T.URL)),
                "account_capabilities": len(service.capability_registry.get_capabilities_for_input(T.ACCOUNT)),
                "url_tasks_executed": result["tasks_executed"], "url_status": result["status"]}
    finally:
        await service.stop()


def host_boundary(root):
    import spider.web.app as web_app
    service = SpiderService(db_path=str(root / "host.db"), artifacts_dir=str(root / "host-runs"))
    with patch.object(web_app, "create_spider_service", return_value=service), TestClient(web_app.create_app()) as client:
        client.post("/api/cases", json={"name": "Synthetic host-boundary audit"})
        response = client.get("/api/cases", headers={"Host": "untrusted.example", "Origin": "http://untrusted.example"})
        return {"untrusted_host_status": response.status_code,
                "synthetic_case_visible": "Synthetic host-boundary audit" in response.text,
                "full_browser_dns_rebinding_exploit": "UNVERIFIED"}


def main():
    with tempfile.TemporaryDirectory(prefix="spider-audit-") as name:
        root = Path(name)
        findings = asyncio.run(engine_findings(root))
        findings["unsupported_input"] = asyncio.run(unsupported_input(root))
        findings["local_api_boundary"] = host_boundary(root)
    print(json.dumps(findings, indent=2))


if __name__ == "__main__":
    main()
