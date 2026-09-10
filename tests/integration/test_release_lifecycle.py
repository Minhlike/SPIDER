import asyncio
import sqlite3

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from spider.service.service import SpiderService
from spider.storage.schema import ProviderRunRecord
from spider.web.api.investigate import (
    StartInvestigationRequest, start_investigation, stop_investigation_run,
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
