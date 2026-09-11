"""Conservative source-declared freshness assessment; never infers disappearance."""
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class SourceFreshnessContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: str = Field(pattern=r"^[a-z0-9_]{2,64}$")
    rule_id: str = Field(pattern=r"^[A-Z0-9_]{3,96}$")
    rule_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    revalidate_after: datetime

    @model_validator(mode="after")
    def require_timezone(self):
        if self.revalidate_after.tzinfo is None:
            raise ValueError("revalidate_after must include a timezone")
        return self


def assess_source_freshness(observations, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    applied, invalid = [], 0
    for observation in observations:
        payload = (observation.observable_metadata or {}).get("source_freshness")
        if payload is None:
            continue
        try:
            contract = SourceFreshnessContract.model_validate(payload)
        except (ValidationError, TypeError):
            invalid += 1
            continue
        if contract.provider_id != observation.provider_id:
            invalid += 1
            continue
        due = contract.revalidate_after <= now
        applied.append({"observation_id": observation.id,
                        "provider_id": observation.provider_id,
                        "rule_id": contract.rule_id,
                        "rule_version": contract.rule_version,
                        "revalidate_after": contract.revalidate_after.isoformat(),
                        "status": "REVALIDATION_DUE" if due else "WITHIN_SOURCE_WINDOW"})
    due_count = sum(row["status"] == "REVALIDATION_DUE" for row in applied)
    if not applied:
        stale_status, reason = "NOT_INFERRED", "NO_SOURCE_SPECIFIC_EXPIRY_RULE"
    elif due_count == len(applied):
        stale_status, reason = "REVALIDATION_DUE", "SOURCE_REVALIDATION_WINDOWS_ENDED"
    elif due_count:
        stale_status, reason = "MIXED_SOURCE_WINDOWS", "SOME_SOURCE_REVALIDATION_WINDOWS_ENDED"
    else:
        stale_status, reason = "WITHIN_SOURCE_WINDOW", "SOURCE_REVALIDATION_WINDOWS_ACTIVE"
    return {"currentness": "UNKNOWN", "stale_status": stale_status, "reason": reason,
            "source_rules_applied": len(applied), "invalid_source_rules_ignored": invalid,
            "rules": applied[:100], "rules_truncated": len(applied) > 100}
