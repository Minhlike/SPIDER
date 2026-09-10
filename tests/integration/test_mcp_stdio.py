"""Real stdio protocol using official client, isolated database, no HTTP listener."""
import sys
from pathlib import Path
import pytest


@pytest.mark.asyncio
async def test_official_client_initialize_discover_and_call(tmp_path):
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from spider.service.service import SpiderService
    from spider.models.enums import ObservableType
    from uuid import uuid4
    import json
    setup = SpiderService(str(tmp_path / "stdio.db"), str(tmp_path / "runs"))
    await setup.start()
    try:
        case = await setup.create_case("Synthetic stdio hypothesis")
        target = await setup.add_target(case["id"], "fixture", ObservableType.USERNAME)
    finally:
        await setup.stop()
    root = Path(__file__).resolve().parents[2]
    server = StdioServerParameters(command=sys.executable, args=[
        "-m", "spider.mcp.stdio", "--root", str(root),
        "--db", str(tmp_path / "stdio.db"), "--artifacts", str(tmp_path / "runs")])
    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            result = await session.initialize()
            assert result.serverInfo.name == "SPIDER"
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {"case_digest", "case_delta", "get_evidence", "graph_neighbors", "compare_runs",
                    "run_coverage", "browser_trace", "phone_candidate_digest", "telemetry", "input_catalogue", "run_capability",
                    "action_status", "cancel_run", "resume_run", "annotate_evidence", "list_cases", "list_targets"} <= names
            call = await session.call_tool("input_catalogue", {})
            assert not call.isError
            missing = await session.call_tool("case_digest", {
                "case_id": "missing", "target_id": "missing"})
            assert "INVALID_SCOPE_OR_ARGUMENT" in str(missing.content)

            payload = {"case_id": case["id"], "target_id": target["id"],
                "action_id": str(uuid4()), "statement": "Unverified synthetic hypothesis",
                "supporting": [], "contradicting": [], "unknown": []}
            created = await session.call_tool("create_hypothesis", payload)
            assert not created.isError
            receipt = json.loads(created.content[0].text)
            assert receipt["label"] == "HYPOTHESIS" and not receipt["identity_verified"]
            repeated = await session.call_tool("create_hypothesis", payload)
            assert json.loads(repeated.content[0].text) == receipt
            listed = await session.call_tool("list_hypotheses", {
                "case_id": case["id"], "target_id": target["id"]})
            assert len(json.loads(listed.content[0].text)["hypotheses"]) == 1


@pytest.mark.asyncio
async def test_stdio_capability_receipt_retry_and_cancel_offline(tmp_path):
    pytest.importorskip("mcp")
    import asyncio
    import json
    from uuid import uuid4
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from spider.service.service import SpiderService
    from spider.models.enums import ObservableType as T
    from spider.models.observable import NormalizedObservable
    from spider.models.observation import Observation
    from spider.models.provenance import SourceLineage
    from spider.storage.repositories.observation_repo import ObservationRepository

    db, artifacts = str(tmp_path / "actions.db"), str(tmp_path / "runs")
    setup = SpiderService(db, artifacts)
    await setup.start()
    try:
        case = (await setup.create_case("Synthetic stdio action"))["id"]
        target = (await setup.add_target(case, "fixture.example", T.DOMAIN))["id"]
        seed = Observation(observable=NormalizedObservable(type=T.DOMAIN, value="fixture.example"),
            lineage=SourceLineage(case_id=case, run_id="seed", task_id="seed", seed_id=target,
                provider_id="seed_target", provider_version="1"))
        async def write(session):
            await ObservationRepository.append_observation(session, seed)
            await setup.resolution_engine.resolve_observations(session, [seed], case)
        await setup.db_writer.submit(write)
        entity = (await setup.get_case_entities(case))[0]["id"]
    finally:
        await setup.stop()
    # A real stdio process with only the existing offline fake adapter registered.
    script = tmp_path / "fixture_stdio.py"
    script.write_text('''import sys
from spider.service.service import SpiderService
from spider.providers.fake.provider_a import FakeProviderA
from spider.mcp.stdio import create_server
s = SpiderService(sys.argv[1], sys.argv[2])
s.provider_manager.register_adapter(FakeProviderA())
s.capability_registry.get_capability("SUBDOMAIN_DISCOVERY").default_providers = ["fake_a"]
create_server(s).run(transport="stdio")
''', encoding="utf-8")
    args = {"case_id": case, "target_id": target, "entity_id": entity, "action_id": str(uuid4()),
            "capability": "SUBDOMAIN_DISCOVERY", "provider_id": "fake_a"}
    params = StdioServerParameters(command=sys.executable, args=[str(script), db, artifacts])
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            async def call(name, payload):
                result = await session.call_tool(name, payload)
                assert not result.isError
                return json.loads(result.content[0].text)
            receipt = await call("run_capability", args)
            assert "error" not in receipt
            async def wait():
                while True:
                    result = await call("action_status", {k: args[k] for k in ("case_id", "target_id", "action_id")})
                    if result["status"] not in {"QUEUED", "RUNNING"}:
                        return result
                    await asyncio.sleep(.02)
            result = await asyncio.wait_for(wait(), 5)
            assert result["status"] == "COMPLETED" and result["observations_count"] == 6
            assert await call("run_capability", args) == result
            listed = await call("list_cases", {})
            assert listed["items"][0]["id"] == case
            targets = await call("list_targets", {"case_id": case})
            assert targets["items"][0]["id"] == target
            scope = {"case_id": case, "target_id": target}
            digest = await call("case_digest", scope)
            evidence = digest["evidence"][0]
            graph = await call("graph_neighbors", {**scope, "entity_id": evidence["entity_id"]})
            annotation = {**scope, "action_id": str(uuid4()), "observation_id": evidence["id"],
                "claim_id": graph["edges"][0]["id"], "role": "SUPPORTING_EVIDENCE"}
            annotated = await call("annotate_evidence", annotation)
            assert annotated["status"] == "ANNOTATED" and not annotated["identity_verified"]
            assert await call("annotate_evidence", annotation) == annotated
            cancelled = await call("cancel_run", {"case_id": case, "target_id": target,
                "action_id": str(uuid4()), "run_id": result["run_id"]})
            # Cancelling a completed run is a no-op, never relabels it as cancelled.
            assert cancelled["status"] == "COMPLETED"
