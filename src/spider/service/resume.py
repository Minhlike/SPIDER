"""Shared admission for resuming a durable full-investigation checkpoint."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from spider.core.checkpoint import decode_frontier, restore_ledger
from spider.models.budget import ExecutionBudget
from spider.models.enums import ExecutionStatus
from spider.models.execution import ProviderRun
from spider.storage.repositories.execution_repo import ExecutionRepository
from spider.storage.schema import ProviderRunRecord


class ResumeError(ValueError):
    pass


@dataclass(frozen=True)
class ResumeSpec:
    source_run_id: str
    run_id: str
    case_id: str
    target: str
    observable_type: str
    budget: ExecutionBudget
    policy_profile: str | None
    investigation_mode: str
    browser_assisted: bool


async def prepare_resume(service, source_run_id: str, *, case_id: str | None = None,
                         target_id: str | None = None,
                         budget: ExecutionBudget | None = None) -> ResumeSpec:
    async with service.db_manager.session_factory() as session:
        previous = await session.get(ProviderRunRecord, source_run_id)
        if previous is None:
            raise ResumeError("RUN_NOT_FOUND")
        if case_id is not None and previous.case_id != case_id:
            raise ResumeError("RUN_OUTSIDE_SCOPE")
        metadata = previous.metadata_json if isinstance(previous.metadata_json, dict) else {}
        checkpoint = metadata.get("checkpoint") or {}
        if previous.status not in {"CANCELLED", "PARTIAL"} or not checkpoint.get("frontier"):
            raise ResumeError("RUN_NOT_RESUMABLE")
        try:
            decoded = decode_frontier(checkpoint["frontier"])
            restore_ledger(metadata.get("budget_ledger"), checkpoint)
        except (KeyError, TypeError, ValueError):
            raise ResumeError("CHECKPOINT_INVALID") from None
        if target_id is not None and {seed for _, seed, _ in decoded} != {target_id}:
            raise ResumeError("CHECKPOINT_OUTSIDE_TARGET")
        if budget is None:
            try:
                budget = ExecutionBudget.model_validate(metadata["budget_limits"])
            except (KeyError, ValueError):
                raise ResumeError("CHECKPOINT_BUDGET_MISSING") from None
            # Finite limits grant one fresh segment on each explicit resume;
            # the restored ledger still reports cumulative physical work.
            ledger = metadata.get("budget_ledger") or {}
            budget.max_entities += int(ledger.get("entities_count") or 0)
            if budget.max_requests is not None:
                budget.max_requests += int(ledger.get("requests_count") or 0)
            if budget.max_provider_calls is not None:
                budget.max_provider_calls += int(ledger.get("provider_calls_count") or 0)
        resolved_case_id = previous.case_id

    new_run_id = str(uuid4())

    async def admit(session):
        source = await session.get(ProviderRunRecord, source_run_id)
        if source is None:
            raise ResumeError("RUN_NOT_FOUND")
        source_metadata = source.metadata_json if isinstance(source.metadata_json, dict) else {}
        if source_metadata.get("resume_child_run_id"):
            raise ResumeError("RUN_ALREADY_RESUMED")
        source.metadata_json = {**source_metadata, "resume_child_run_id": new_run_id}
        await ExecutionRepository.create_provider_run(session, ProviderRun(
            id=new_run_id, case_id=resolved_case_id, status=ExecutionStatus.QUEUED,
            metadata={"resumed_from_run_id": source_run_id,
                      "budget_limits": budget.model_dump(mode="json")}
        ))
    await service.db_writer.submit(admit)
    first, _, _ = decoded[0]
    return ResumeSpec(source_run_id=source_run_id, run_id=new_run_id,
        case_id=resolved_case_id, target=first.canonical_value,
        observable_type=first.type.value, budget=budget,
        policy_profile=metadata.get("policy_profile"),
        investigation_mode=metadata.get("investigation_mode") or "AUTO",
        browser_assisted=bool(metadata.get("browser_assisted")))
