"""Manual, versioned canary-result ingestion. Never schedules or runs live accounts."""
import hashlib
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field
from spider.storage.schema import ProviderAuditRecord

LABELS = {"EXISTS", "NOT_EXISTS", "SOFT_404", "RATE_LIMIT", "LOGIN_WALL"}


class CanaryResult(BaseModel):
    label: Literal["EXISTS", "NOT_EXISTS", "SOFT_404", "RATE_LIMIT", "LOGIN_WALL"]
    result: Literal["CONFIRMED", "NOT_FOUND", "UNKNOWN", "RATE_LIMITED", "BLOCKED"]


class CanaryReport(BaseModel):
    provider_version: str = Field(max_length=64)
    adapter_version: str = Field(max_length=64)
    results: list[CanaryResult] = Field(min_length=5, max_length=1000)
    dataset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


async def ingest_canary(session, provider_id, report):
    if {r.label for r in report.results} != LABELS:
        raise ValueError("Canary report requires all five label classes")
    expected = {"EXISTS": {"CONFIRMED"}, "NOT_EXISTS": {"NOT_FOUND"}, "SOFT_404": {"UNKNOWN"},
                "RATE_LIMIT": {"RATE_LIMITED"}, "LOGIN_WALL": {"UNKNOWN", "BLOCKED"}}
    false_positive = any(r.label != "EXISTS" and r.result == "CONFIRMED" for r in report.results)
    failures = sum(r.result not in expected[r.label] for r in report.results)
    rec = await session.get(ProviderAuditRecord, provider_id)
    if rec is None:
        rec = ProviderAuditRecord(provider_id=provider_id, failure_streak=0, success_streak=0)
        session.add(rec)
    rec.failure_streak = (rec.failure_streak or 0) + 1 if failures else 0
    rec.success_streak = (rec.success_streak or 0) + 1 if not failures else 0
    was_quarantined = rec.state == "QUARANTINED"
    rec.state = ("QUARANTINED" if false_positive or rec.failure_streak >= 2 or (was_quarantined and rec.success_streak < 2)
                 else "DEGRADED" if failures else "CONTRACT_PASSED")
    rec.provider_version, rec.adapter_version = report.provider_version, report.adapter_version
    rec.report_sha256 = hashlib.sha256(report.model_dump_json().encode()).hexdigest()
    rec.checked_at = datetime.now(timezone.utc)
    return {"provider_id": provider_id, "state": rec.state, "failures": failures, "live_verified": False,
            "report_sha256": rec.report_sha256, "label": "EXPERIMENT RESULT"}
