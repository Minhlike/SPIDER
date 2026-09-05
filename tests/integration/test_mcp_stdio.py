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
            assert {"case_digest", "get_evidence", "graph_neighbors", "compare_runs",
                    "run_coverage", "telemetry", "input_catalogue"} <= names
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
