import json

import pytest

from spider.mcp.server import SpiderMCPServer
from spider.models.enums import ObservableType as T
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage
from spider.service.service import SpiderService
from spider.storage.repositories.observation_repo import ObservationRepository


@pytest.mark.asyncio
async def test_digest_pagination_scope_and_shared_lifecycle(tmp_path):
    service = SpiderService(str(tmp_path / "digest.db"), str(tmp_path / "runs"))
    await service.start()
    try:
        case = await service.create_case("Synthetic digest")
        first = await service.add_target(case["id"], "first", T.USERNAME)
        other = await service.add_target(case["id"], "other", T.USERNAME)
        observations = []
        for target, name in ((first, "first"), (other, "other")):
            for i in range(3):
                observations.append(Observation(
                    observable=NormalizedObservable(type=T.ACCOUNT, value=f"{name}{i}@fixture"),
                    lineage=SourceLineage(case_id=case["id"], seed_id=target["id"],
                        run_id="fixture-run", task_id="fixture-task", provider_id="fixture",
                        provider_version="1", parent_observable_value=name,
                        parent_observable_type=T.USERNAME),
                    raw_data={"secret": "must-not-export", "large": "x" * 10000}))
        await service.db_writer.submit(lambda session:
            ObservationRepository.append_observations_batch(session, observations))
        server = SpiderMCPServer(service)
        args = {"case_id": case["id"], "target_id": first["id"], "limit": 2}
        page = await server.handle_tool_call("case_digest", args)
        assert page["counts"]["evidence"] == 3
        assert len(page["evidence"]) == 2 and page["more"]
        assert "must-not-export" not in json.dumps(page)
        assert len(json.dumps(page)) < 4000
        tail = await server.handle_tool_call("case_digest", {**args, "after": page["next_cursor"]})
        assert len(tail["evidence"]) == 1 and not tail["more"]
        assert not {o["id"] for o in page["evidence"]} & {o["id"] for o in tail["evidence"]}
        wrong = await server.handle_tool_call("get_evidence", {
            **args, "target_id": other["id"], "observation_id": observations[0].id})
        assert wrong["error"]["code"] == "INVALID_SCOPE_OR_ARGUMENT"
        valid = await server.handle_tool_call("get_evidence", {**args, "observation_id": observations[0].id})
        assert valid["seed_id"] == first["id"] and not valid["raw_payload_included"]
        assert "error" in await server.handle_tool_call("case_digest", {**args, "limit": 101})
        assert "error" in await server.handle_tool_call("case_digest", {**args, "after": observations[3].id})
        assert service.is_running
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_unknown_tool_does_not_start_service(tmp_path):
    service = SpiderService(str(tmp_path / "unknown.db"), str(tmp_path / "runs"))
    assert "error" in await SpiderMCPServer(service).handle_tool_call("unknown", {})
    assert not service.is_running
