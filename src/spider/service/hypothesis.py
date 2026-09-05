"""Persist bounded competing hypotheses without changing source observations."""
import hashlib
import json
from uuid import UUID
from datetime import timezone
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from spider.service.projection import project
from spider.storage.schema import HypothesisRecord


class HypothesisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: UUID
    target_id: str = Field(min_length=1, max_length=64)
    statement: str = Field(min_length=1, max_length=1000)
    supporting: list[str] = Field(default_factory=list, max_length=50)
    contradicting: list[str] = Field(default_factory=list, max_length=50)
    unknown: list[str] = Field(default_factory=list, max_length=50)


def public_hypothesis(row):
    evidence = row.evidence_json
    return {"id": row.id, "statement": row.statement, "evidence": evidence,
            "label": "HYPOTHESIS", "identity_verified": False,
            "created_at": row.created_at.replace(tzinfo=timezone.utc).isoformat(),
            "assessment": "COMPETING_EVIDENCE" if evidence["contradicting"] else "REVIEW_REQUIRED",
            "source_independence": "NOT_YET_VERIFIED"}


async def create_hypothesis(session, case_id, request):
    view = await project(session, case_id, request.target_id)
    if view.seed is None or view.seed.id != request.target_id:
        raise ValueError("Explicit target required")
    ids = {o.id for o in view.evidence_observations}
    groups = {k: sorted(set(getattr(request, k))) for k in ("supporting", "contradicting", "unknown")}
    if any(set(g) - ids for g in groups.values()):
        raise ValueError("Evidence outside hypothesis scope")
    if len(set().union(*map(set, groups.values()))) != sum(map(len, groups.values())):
        raise ValueError("Evidence cannot have competing roles in the same hypothesis")
    key = hashlib.sha256(f"{case_id}|{request.action_id}".encode()).hexdigest()
    digest = hashlib.sha256(json.dumps({"target": request.target_id,
        "statement": request.statement, "evidence": groups}, sort_keys=True).encode()).hexdigest()
    prior = await session.get(HypothesisRecord, key)
    if prior:
        if prior.payload_sha256 != digest:
            raise ValueError("Action ID already used with different arguments")
        return public_hypothesis(prior)
    row = HypothesisRecord(id=key, case_id=case_id, seed_id=request.target_id,
        statement=request.statement, evidence_json=groups, payload_sha256=digest)
    session.add(row)
    await session.flush()
    return public_hypothesis(row)


async def list_hypotheses(session, case_id, target_id, limit=20):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid limit")
    await project(session, case_id, target_id)
    rows = list((await session.scalars(select(HypothesisRecord).where(
        HypothesisRecord.case_id == case_id, HypothesisRecord.seed_id == target_id)
        .order_by(HypothesisRecord.created_at, HypothesisRecord.id).limit(limit + 1))).all())
    return {"hypotheses": [public_hypothesis(row) for row in rows[:limit]], "more": len(rows) > limit}
