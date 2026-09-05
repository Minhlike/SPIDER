from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from spider.storage.schema import TaskRunRecord, ProviderRunRecord, ExecutionLedgerRecord
from spider.models.execution import TaskRun, ProviderRun

class ExecutionRepository:
    @staticmethod
    async def has_executed(session: AsyncSession, case_id: str, execution_key_hash: str) -> bool:
        result = await session.execute(
            select(ExecutionLedgerRecord).where(
                ExecutionLedgerRecord.case_id == case_id,
                ExecutionLedgerRecord.execution_key_hash == execution_key_hash
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def mark_executed(session: AsyncSession, case_id: str, execution_key_hash: str, status: str = "COMPLETED") -> ExecutionLedgerRecord:
        rec = ExecutionLedgerRecord(
            id=f"{case_id}_{execution_key_hash[:16]}",
            case_id=case_id,
            execution_key_hash=execution_key_hash,
            status=status
        )
        session.add(rec)
        return rec

    @staticmethod
    async def create_provider_run(session: AsyncSession, run: ProviderRun) -> ProviderRunRecord:
        rec = ProviderRunRecord(
            id=run.id,
            case_id=run.case_id,
            status=run.status.value,
            started_at=run.started_at,
            completed_at=run.completed_at,
            tasks_count=run.tasks_count,
            observations_count=run.observations_count,
            metadata_json=run.metadata,
            error_message=run.error_message
        )
        session.add(rec)
        return rec

    @staticmethod
    async def update_provider_run(session: AsyncSession, run: ProviderRun) -> Optional[ProviderRunRecord]:
        result = await session.execute(select(ProviderRunRecord).where(ProviderRunRecord.id == run.id))
        rec = result.scalar_one_or_none()
        if rec:
            rec.status = run.status.value
            rec.completed_at = run.completed_at
            rec.tasks_count = run.tasks_count
            rec.observations_count = run.observations_count
            rec.metadata_json = run.metadata
            rec.error_message = run.error_message
            return rec
        return None

    @staticmethod
    async def create_task_run(session: AsyncSession, task: TaskRun) -> TaskRunRecord:
        rec = TaskRunRecord(
            id=task.id,
            case_id=task.case_id,
            run_id=task.run_id,
            execution_key_hash=task.execution_key_hash,
            provider_id=task.provider_id,
            capability=task.capability,
            target_observable_value=task.target_observable_value,
            status=task.status.value,
            started_at=task.started_at,
            completed_at=task.completed_at,
            error_message=task.error_message,
            observations_count=task.observations_count,
            raw_artifact_id=task.raw_artifact_id,
            metadata_json=task.metadata
        )
        session.add(rec)
        return rec
