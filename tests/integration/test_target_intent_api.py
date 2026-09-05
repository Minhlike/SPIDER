import asyncio

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from spider.service.service import SpiderService


@pytest.fixture
def intent_app(tmp_path, monkeypatch):
    import spider.web.app as web_app
    service = SpiderService(db_path=str(tmp_path / "intent.db"), artifacts_dir=str(tmp_path / "runs"))
    seen = []

    async def investigate(case_id, **kwargs):
        from spider.storage.repositories.case_repo import CaseRepository
        async with service.db_manager.session_factory() as session:
            targets = await CaseRepository.get_targets(session, case_id)
            seen.extend((t.observable_type, t.canonical_value, t.metadata_json) for t in targets)
        return {"status": "COMPLETED"}

    monkeypatch.setattr(service, "investigate", investigate)
    monkeypatch.setattr(web_app, "create_spider_service", lambda **kwargs: service)
    with TestClient(web_app.create_app()) as client:
        yield client, service, seen


def test_ambiguous_or_invalid_input_cannot_create_case_or_run(intent_app):
    client, service, seen = intent_app
    for payload in ({"target": "alice.dev"}, {"target": "1234567890"},
                    {"target": "-bad.com", "target_type": "DOMAIN"}, {"target": ""}):
        assert client.post("/api/investigate", json=payload).status_code == 422
    assert client.get("/api/cases").json() == []
    assert not service.background_tasks
    assert not seen


@pytest.mark.parametrize("target,choice,kind,canonical", [
    ("ms.orianawren", None, "USERNAME", "ms.orianawren"),
    ("@Mixed.Case", None, "USERNAME", "Mixed.Case"),
    ("alice.dev", "USERNAME", "USERNAME", "alice.dev"),
    ("alice.dev", "DOMAIN", "DOMAIN", "alice.dev"),
])
def test_selected_intent_reaches_saved_target_and_engine(intent_app, target, choice, kind, canonical):
    client, service, seen = intent_app
    response = client.post("/api/investigate", json={"target": target, "target_type": choice})
    assert response.status_code == 200
    assert response.json()["type"] == kind
    async def drain():
        if service.background_tasks:
            await asyncio.gather(*service.background_tasks)
    client.portal.call(drain)
    assert seen[0][:2] == (kind, canonical)
    assert seen[0][2]["classification"]["confidence_kind"] == "heuristic_not_probability"


def test_classification_preview_api_validates_request(intent_app):
    client, _, _ = intent_app
    dotted = client.post("/api/classify", json={"target": "ms.orianawren"}).json()
    assert [s["provider_id"] for s in dotted["source_preflight"]["sources"]] == []
    assert not dotted["source_preflight"]["internet_api_keys_applicable"]
    assert client.post("/api/classify", json={"target": "alice.dev"}).json()["needs_confirmation"]
    assert client.post("/api/classify", json={"target": "alice.dev", "target_type": "USERNAME"}).json()["type"] == "USERNAME"
    for payload in ([], {"target": 123}, {"target": "@"}, {"target": "alice", "target_type": "invalid"}):
        assert client.post("/api/classify", json=payload).status_code == 422


def test_cli_rejects_ambiguity_before_creating_service(monkeypatch):
    import spider.cli.main as cli
    def denied(**kwargs):
        pytest.fail("Ambiguous input started a service")
    monkeypatch.setattr(cli, "create_spider_service", denied)
    result = CliRunner().invoke(cli.app, ["investigate", "alice.dev"])
    assert result.exit_code == 2
    assert "--type" in result.output


@pytest.mark.asyncio
async def test_mcp_rejects_ambiguity_before_starting_service(tmp_path, monkeypatch):
    from spider.mcp.server import create_mcp_server
    service = SpiderService(db_path=str(tmp_path / "not-created.db"), artifacts_dir=str(tmp_path / "runs"))
    async def denied():
        pytest.fail("Ambiguous input started a service")
    monkeypatch.setattr(service, "start", denied)
    result = await create_mcp_server(service).handle_tool_call("collect", {"target": "alice.dev"})
    assert result["error"]["code"] == "ambiguous_target"
    assert not (tmp_path / "not-created.db").exists()
