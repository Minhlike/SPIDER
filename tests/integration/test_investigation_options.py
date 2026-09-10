import asyncio

from fastapi.testclient import TestClient

from spider.service.service import SpiderService


def test_browser_budget_and_authorization_reach_engine(tmp_path, monkeypatch):
    import spider.web.app as web_app
    service = SpiderService(db_path=str(tmp_path / "options.db"), artifacts_dir=str(tmp_path / "runs"))
    seen = {}
    async def investigate(case_id, budget, policy_profile, run_id, investigation_mode,
                          browser_assisted):
        seen.update(budget=budget, profile=policy_profile, mode=investigation_mode,
                    browser_assisted=browser_assisted)
        async with service.db_manager.session_factory() as session:
            from spider.storage.repositories.case_repo import CaseRepository
            seen["authorized"] = (await CaseRepository.get_targets(session, case_id))[0].scope_authorized
        return {"status": "COMPLETED"}
    monkeypatch.setattr(service, "investigate", investigate)
    monkeypatch.setattr(web_app, "create_spider_service", lambda **kwargs: service)
    with TestClient(web_app.create_app()) as client:
        response = client.post("/api/investigate", json={"target": "fixture-user", "scope_authorized": True,
            "budget": {"max_depth": 0, "max_entities": 100, "timeout_seconds": 30, "username_site_limit": 50}})
        assert response.json()["status"] == "QUEUED"
        # Drain the actual background task on the app's event loop.
        async def drain():
            if service.background_tasks: await asyncio.gather(*service.background_tasks)
        client.portal.call(drain)
        assert seen["budget"].max_runtime_seconds == 30
        assert seen["budget"].username_site_limit == 50
        assert seen["budget"].username_source_scope == "VN_COMMON_CORE"
        assert seen["mode"] == "PERSONAL_FOOTPRINT"
        assert seen["browser_assisted"] is False
        assert seen["budget"].max_depth == 0
        assert seen["authorized"] is True
        assert client.post("/api/investigate", json={"target": "fixture-user",
            "budget": {"timeout_seconds": -1}}).status_code == 422
        rejected = client.post("/api/investigate", json={
            "target": "fixture-user", "browser_assisted": True,
            "scope_authorized": False,
        })
        assert rejected.status_code == 422
        assert rejected.json()["detail"]["code"] == "browser_scope_authorization_required"


def test_unlimited_time_and_request_options_reach_engine_as_null(tmp_path, monkeypatch):
    import spider.web.app as web_app
    service = SpiderService(db_path=str(tmp_path / "unlimited.db"), artifacts_dir=str(tmp_path / "runs"))
    seen = {}

    async def investigate(case_id, budget, policy_profile, run_id, investigation_mode,
                          browser_assisted):
        seen["budget"] = budget
        return {"status": "COMPLETED"}

    monkeypatch.setattr(service, "investigate", investigate)
    monkeypatch.setattr(web_app, "create_spider_service", lambda **kwargs: service)
    with TestClient(web_app.create_app()) as client:
        response = client.post("/api/investigate", json={
            "target": "example.test",
            "target_type": "DOMAIN",
            "budget": {
                "max_depth": 0,
                "max_entities": 500,
                "max_requests": None,
                "timeout_seconds": None,
            },
        })
        assert response.status_code == 200
        assert response.json()["status"] == "QUEUED"

        async def drain():
            if service.background_tasks:
                await asyncio.gather(*service.background_tasks)
        client.portal.call(drain)

        assert seen["budget"].max_requests is None
        assert seen["budget"].max_runtime_seconds is None
        assert seen["budget"].max_provider_calls is None
