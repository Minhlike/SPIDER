"""Operator evidence annotations; they cannot verify ownership or change observations."""
import hashlib
from typing import Literal
from pydantic import BaseModel
from sqlalchemy import select
from spider.storage.schema import EvidenceReviewRecord
from spider.service.projection import project
from spider.service.evidence_analysis import assess_hypothesis


class EvidenceReview(BaseModel):
    target_id: str
    claim_id: str
    observation_id: str
    role: Literal["SUPPORTING_EVIDENCE", "CONTRADICTING_EVIDENCE", "UNKNOWN"]
    dependency: Literal["INDEPENDENT_SOURCE", "DERIVED_SOURCE", "MIRRORED_SOURCE", "UNKNOWN_DEPENDENCY"] = "UNKNOWN_DEPENDENCY"
    origin_id: str | None = None


async def save_review(session, case_id, review):
    view = await project(session, case_id, review.target_id)
    ids = {o.id for o in view.evidence_observations}
    if review.claim_id not in {a.id for a in view.assertions} or review.observation_id not in ids or (review.origin_id and review.origin_id not in ids):
        raise ValueError("Review evidence must belong to the selected target and claim")
    if review.dependency != "UNKNOWN_DEPENDENCY" and not review.origin_id:
        raise ValueError("Dependency claims require an origin observation")
    key = hashlib.sha256(f"{case_id}|{review.target_id}|{review.claim_id}|{review.observation_id}".encode()).hexdigest()
    rec = await session.get(EvidenceReviewRecord, key)
    if rec is None:
        rec = EvidenceReviewRecord(id=key, case_id=case_id, seed_id=review.target_id)
        session.add(rec)
    for name in ("claim_id", "observation_id", "role", "dependency", "origin_id"):
        setattr(rec, name, getattr(review, name))
    return {"status": "ANNOTATED", "identity_verified": False}


async def hypotheses(session, case_id, view):
    if not view.seed:
        return []
    reviews = list((await session.scalars(select(EvidenceReviewRecord).where(
        EvidenceReviewRecord.case_id == case_id, EvidenceReviewRecord.seed_id == view.seed.id))).all())
    ids, claims = {o.id for o in view.observations}, {a.id for a in view.assertions}
    groups = {}
    for r in reviews:
        if r.claim_id in claims and r.observation_id in ids:
            groups.setdefault(r.claim_id, []).append({"id": r.observation_id, "role": r.role,
                "dependency": r.dependency, "origin_id": r.origin_id})
    return [{"claim_id": key, **assess_hypothesis(items)} for key, items in sorted(groups.items())]
