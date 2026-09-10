import asyncio
import sqlite3

import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient

from spider.service.service import SpiderService
from spider.mcp.server import SpiderMCPServer
from spider.models.enums import ObservableType
from spider.storage.schema import ProviderRunRecord
from spider.web.api.investigate import (
    ResumeInvestigationRequest, StartInvestigationRequest,
    resume_investigation_run, start_investigation, stop_investigation_run,
)
from spider.web.app import create_app


@pytest.mark.asyncio
async def test_queued_run_persisted_and_shutdown_cancels_cleanly(tmp_path, monkeypatch):
    database = tmp_path / "lifecycle.db"
    service = SpiderService(db_path=str(database), artifacts_dir=str(tmp_path / "runs"))
    started = asyncio.Event()
    async def blocked(**kwargs):
        started.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(service, "investigate", blocked)
    await service.start()
    try:
        result = await start_investigation(StartInvestigationRequest(target="example.com", target_type="DOMAIN"), BackgroundTasks(), service)
        assert result["status"] == "QUEUED"
        await asyncio.wait_for(started.wait(), 3)
        async with service.db_manager.session_factory() as session:
            run = await session.get(ProviderRunRecord, result["run_id"])
            assert run.case_id == result["case_id"]
            assert run.status == "QUEUED"
    finally:
        await service.stop()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT status FROM provider_runs").fetchall() == [("CANCELLED",)]
    assert not service.background_tasks and not service.is_running


@pytest.mark.asyncio
async def test_background_failure_persists_terminal_status(tmp_path, monkeypatch):
    service = SpiderService(db_path=str(tmp_path / "failure.db"), artifacts_dir=str(tmp_path / "runs"))
    async def fail(**kwargs):
        raise RuntimeError("untrusted provider error")
    monkeypatch.setattr(service, "investigate", fail)
    await service.start()
    try:
        result = await start_investigation(StartInvestigationRequest(target="example.com", target_type="DOMAIN"), BackgroundTasks(), service)
        await asyncio.gather(*list(service.background_tasks))
        async with service.db_manager.session_factory() as session:
            run = await session.get(ProviderRunRecord, result["run_id"])
            assert run.status == "FAILED"
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_user_can_stop_one_run_without_stopping_service(tmp_path, monkeypatch):
    service = SpiderService(db_path=str(tmp_path / "stop-one.db"), artifacts_dir=str(tmp_path / "runs"))
    started = asyncio.Event()

    async def blocked(**kwargs):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "investigate", blocked)
    await service.start()
    try:
        result = await start_investigation(
            StartInvestigationRequest(target="example.test", target_type="DOMAIN"),
            BackgroundTasks(), service)
        await asyncio.wait_for(started.wait(), 3)

        stopped = await stop_investigation_run(result["run_id"], service)

        assert stopped == {"run_id": result["run_id"], "case_id": result["case_id"],
                           "status": "CANCELLED"}
        assert service.is_running is True
        assert not service.background_tasks
        async with service.db_manager.session_factory() as session:
            assert (await session.get(ProviderRunRecord, result["run_id"])).status == "CANCELLED"
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_user_can_resume_a_durable_checkpoint_as_a_new_run(tmp_path, monkeypatch):
    service = SpiderService(db_path=str(tmp_path / "resume-run.db"), artifacts_dir=str(tmp_path / "runs"))
    seen = {}

    async def completed(**kwargs):
        seen.update(kwargs)
        return {"run_id": kwargs["run_id"], "status": "COMPLETED"}

    monkeypatch.setattr(service, "investigate", completed)
    await service.start()
    try:
        old_id = "old-run"
        case_id = (await service.create_case("Resume API fixture"))["id"]
        async def seed(session):
            session.add(ProviderRunRecord(id=old_id, case_id=case_id,
                status="CANCELLED", metadata_json={
                "budget_limits": {"max_depth": 0, "max_entities": 20, "max_requests": None,
                    "max_runtime_seconds": None, "max_provider_calls": None},
                "investigation_mode": "INFRASTRUCTURE", "browser_assisted": False,
                "checkpoint": {"version": 1, "frontier": [{
                    "observable_type": "DOMAIN", "namespace": "", "value": "example.test",
                    "canonical_value": "example.test", "seed_id": "seed", "depth": 0}]}}))
        await service.db_writer.submit(seed)

        result = await resume_investigation_run(old_id, ResumeInvestigationRequest(), service)
        await asyncio.gather(*list(service.background_tasks))

        assert result["resumed_from_run_id"] == old_id and result["run_id"] != old_id
        assert seen["resume_from_run_id"] == old_id
        assert seen["budget"].max_requests is None and seen["budget"].max_runtime_seconds is None
        with pytest.raises(HTTPException) as duplicate:
            await resume_investigation_run(old_id, ResumeInvestigationRequest(), service)
        assert duplicate.value.status_code == 409
        assert duplicate.value.detail["code"] == "run_already_resumed"
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_restart_marks_orphaned_checkpoint_as_resumable_cancelled(tmp_path):
    database = tmp_path / "crash-checkpoint.db"
    artifacts = tmp_path / "runs"
    first = SpiderService(db_path=str(database), artifacts_dir=str(artifacts))
    await first.start()
    case_id = (await first.create_case("Crash recovery fixture"))["id"]
    async def seed(session):
        session.add(ProviderRunRecord(id="orphaned-run", case_id=case_id, status="RUNNING",
            metadata_json={"checkpoint": {"version": 1, "frontier": [{
                "observable_type": "DOMAIN", "namespace": "", "value": "example.test",
                "canonical_value": "example.test", "seed_id": "seed", "depth": 0}]}}))
    await first.db_writer.submit(seed)
    await first.stop()
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE provider_runs SET status='RUNNING', completed_at=NULL WHERE id='orphaned-run'")

    restarted = SpiderService(db_path=str(database), artifacts_dir=str(artifacts))
    await restarted.start()
    try:
        async with restarted.db_manager.session_factory() as session:
            recovered = await session.get(ProviderRunRecord, "orphaned-run")
            assert recovered.status == "CANCELLED" and recovered.completed_at is not None
    finally:
        await restarted.stop()


@pytest.mark.asyncio
async def test_mcp_resume_is_restricted_to_the_checkpoint_seed(tmp_path, monkeypatch):
    service = SpiderService(db_path=str(tmp_path / "mcp-resume.db"), artifacts_dir=str(tmp_path / "runs"))
    async def completed(**kwargs):
        return {"run_id": kwargs["run_id"], "status": "COMPLETED"}
    monkeypatch.setattr(service, "investigate", completed)
    await service.start()
    try:
        case_id = (await service.create_case("Scoped resume fixture"))["id"]
        target_id = (await service.add_target(case_id, "example.test", ObservableType.DOMAIN))["id"]
        async def seed(session):
            session.add(ProviderRunRecord(id="scoped-old", case_id=case_id, status="CANCELLED",
                metadata_json={"budget_limits": {"max_depth": 0}, "checkpoint": {
                    "version": 1, "frontier": [{"observable_type": "DOMAIN", "namespace": "",
                        "value": "example.test", "canonical_value": "example.test",
                        "seed_id": target_id, "depth": 0}]}}))
        await service.db_writer.submit(seed)
        server = SpiderMCPServer(service)

        rejected = await server.handle_tool_call("resume_run", {
            "case_id": case_id, "target_id": "different-seed", "run_id": "scoped-old"})
        assert rejected["error"]["code"] == "CHECKPOINT_OUTSIDE_TARGET"
        resumed = await server.handle_tool_call("resume_run", {
            "case_id": case_id, "target_id": target_id, "run_id": "scoped-old"})
        assert resumed["status"] == "QUEUED" and resumed["automatic_replay"] is False
        await asyncio.gather(*list(service.background_tasks))
    finally:
        await service.stop()


def test_readiness_does_not_run_provider_diagnostics(tmp_path, monkeypatch):
    import spider.web.app as web_app
    service = SpiderService(db_path=str(tmp_path / "ready.db"), artifacts_dir=str(tmp_path / "runs"))
    monkeypatch.setattr(web_app, "create_spider_service", lambda **kwargs: service)
    async def forbidden():
        pytest.fail("Readiness must not run external provider diagnostics")
    monkeypatch.setattr(service, "doctor", forbidden)
    with TestClient(create_app()) as client:
        result = client.get("/api/health?ready=true")
        assert result.status_code == 200
        assert result.json()["database_connected"] is True
        assert result.json()["pid"] > 0
