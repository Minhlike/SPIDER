import json

import httpx
import pytest
from sqlalchemy import select

from spider.models.budget import ExecutionBudget
from spider.models.enums import ObservableType
from spider.providers.whatismyip import WhatIsMyIPAdapter
from spider.service.insights import CaseInsightsBuilder
from spider.service.service import SpiderService
from spider.storage.schema import EgressRecord


@pytest.mark.asyncio
async def test_whatismyip_runs_through_engine_and_builds_sourced_report(tmp_path, caplog):
    secret = "synthetic-whatismyip-secret"

    def upstream(request):
        assert request.headers.get("x-api-key") == secret
        if request.url.path.startswith("/ip-address-lookup/"):
            return httpx.Response(200, json={
                "ip": "8.8.8.8", "country": "United States", "region": "California",
                "city": "Mountain View", "postal_code": "94035", "isp": "Google LLC",
                "asn": "AS15169", "latitude": 37.4, "longitude": -122.1,
                "time_zone": "America/Los_Angeles",
            })
        if request.url.path.startswith("/proxy-check/"):
            return httpx.Response(200, json={
                "is_proxy": False, "proxy_type": None,
                "proxy_type_description": "No proxy detected", "proxy_range": None,
            })
        raise AssertionError("Unexpected endpoint")

    service = SpiderService(db_path=str(tmp_path / "ip.db"), artifacts_dir=str(tmp_path / "runs"))
    service.provider_manager.register_adapter(
        WhatIsMyIPAdapter(lambda: secret, httpx.MockTransport(upstream)))
    await service.start()
    try:
        case = await service.create_case("Synthetic IP intelligence")
        target = await service.add_target(case["id"], "8.8.8.8", ObservableType.IP_ADDRESS)
        result = await service.investigate(case["id"], ExecutionBudget(
            max_depth=0, max_requests=2, diminishing_returns_cutoff=10))
        async with service.db_manager.session_factory() as session:
            events = list((await session.scalars(select(EgressRecord))).all())
            insights = await CaseInsightsBuilder.build_insights(
                session, case["id"], None, target["id"])

        assert result["status"] == "COMPLETED"
        assert result["budget_exhausted"] is False
        assert result["budget_ledger"]["requests_count"] == 2
        assert len(events) == 2
        assert {event.destination for event in events} == {"wimi-api.whatismyip.com"}
        assert {event.purpose for event in events} == {
            "ip_geolocation_lookup", "ip_proxy_classification"}
        assert all(event.authentication == "CREDENTIALED" for event in events)
        report = insights["ip_insights"]
        assert report["asn"] == "AS15169"
        assert report["isp"] == "Google LLC"
        assert report["city"] == "Mountain View"
        assert report["is_proxy"] is False
        assert report["proxy_type_description"] == "No proxy detected"
        assert report["source_observations"][0]["provider_id"] == "whatismyip"
        dumped = json.dumps(insights)
        assert secret not in dumped and secret not in caplog.text
        assert all(secret.encode() not in path.read_bytes()
                   for path in (tmp_path / "runs").rglob("*") if path.is_file())
    finally:
        await service.stop()
