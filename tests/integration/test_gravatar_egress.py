import json

import httpx
import pytest
from sqlalchemy import select

from spider.models.budget import ExecutionBudget
from spider.models.enums import ObservableType
from spider.providers.native.gravatar import GravatarPublicProfileAdapter, gravatar_email_hash
from spider.service.insights import CaseInsightsBuilder
from spider.service.service import SpiderService
from spider.storage.schema import EgressRecord


@pytest.mark.asyncio
async def test_email_profile_request_and_derived_egress_are_auditable(tmp_path):
    email = "owner@example.invalid"

    def upstream(request):
        return httpx.Response(200, json={
            "hash": gravatar_email_hash(email),
            "profile_url": "https://gravatar.com/public-owner",
            "display_name": "Public Owner",
            "description": "Synthetic public profile",
            "location": "Viet Nam",
            "job_title": "Researcher",
            "company": "Example",
            "verified_accounts": [],
        })

    service = SpiderService(db_path=str(tmp_path / "gravatar.db"),
                            artifacts_dir=str(tmp_path / "runs"))
    service.provider_manager.register_adapter(
        GravatarPublicProfileAdapter(httpx.MockTransport(upstream)))
    await service.start()
    try:
        case = await service.create_case("Gravatar fixture")
        target = await service.add_target(case["id"], email, ObservableType.EMAIL,
                                          scope_authorized=True)
        result = await service.investigate(case["id"], ExecutionBudget(
            max_depth=0, max_requests=2, diminishing_returns_cutoff=10))
        async with service.db_manager.session_factory() as session:
            events = list((await session.scalars(select(EgressRecord))).all())
            insights = await CaseInsightsBuilder.build_insights(
                session, case["id"], None, target["id"])
        assert result["budget_ledger"]["requests_count"] == 1
        assert len(events) == 1
        event = events[0]
        assert event.provider_id == "gravatar_public"
        assert event.destination == "api.gravatar.com"
        assert event.purpose == "public_profile_lookup"
        assert event.identifier_type == "EMAIL_SHA256"
        assert event.derivation == "DERIVED"
        assert event.authentication == "ANONYMOUS"
        receipt = next(p for p in insights["provider_contributions"]
                       if p["provider_id"] == "gravatar_public")
        assert receipt["execution_state"] == "CALLED"
        assert receipt["request_count"] == 1 and receipt["contributed"]
        assert receipt["collection_reason"] == "PUBLIC_PROFILE_FOUND"
        assert receipt["scope"] == "Public Gravatar profile for the primary email hash"
        assert insights["profile_evidence"]["exact_email_matches"] == 1
        assert insights["public_profiles"][0]["match_basis"] == "email_hash_public_profile"
        assert insights["public_profiles"][0]["location"] == "Viet Nam"
        assert insights["public_profiles"][0]["job_title"] == "Researcher"
        assert insights["public_profiles"][0]["company"] == "Example"
        dumped = json.dumps([{column.name: str(getattr(event, column.name))
                              for column in EgressRecord.__table__.columns}])
        assert email not in dumped.casefold()
        assert all(email.encode() not in path.read_bytes()
                   for path in (tmp_path / "runs").rglob("*") if path.is_file())
    finally:
        await service.stop()
