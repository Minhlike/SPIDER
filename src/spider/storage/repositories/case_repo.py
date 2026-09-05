from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from spider.storage.schema import CaseRecord, TargetRecord
from spider.models.case import Case
from spider.models.target import Target

class CaseRepository:
    @staticmethod
    async def create_case(session: AsyncSession, case: Case) -> CaseRecord:
        record = CaseRecord(
            id=case.id,
            name=case.name,
            description=case.description,
            tags=case.tags,
            status=case.status,
            created_at=case.created_at,
            updated_at=case.updated_at,
            metadata_json=case.metadata
        )
        session.add(record)
        return record

    @staticmethod
    async def get_case(session: AsyncSession, case_id: str) -> Optional[CaseRecord]:
        result = await session.execute(select(CaseRecord).where(CaseRecord.id == case_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_cases(session: AsyncSession) -> List[CaseRecord]:
        result = await session.execute(select(CaseRecord).order_by(CaseRecord.created_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def add_target(session: AsyncSession, target: Target) -> TargetRecord:
        record = TargetRecord(
            id=target.id,
            case_id=target.case_id,
            observable_type=target.observable_type.value,
            namespace=target.namespace,
            raw_input=target.raw_input,
            canonical_value=target.canonical_value,
            scope_authorized=target.scope_authorized,
            created_at=target.created_at,
            metadata_json=target.metadata
        )
        session.add(record)
        return record

    @staticmethod
    async def get_targets(session: AsyncSession, case_id: str) -> List[TargetRecord]:
        result = await session.execute(select(TargetRecord).where(TargetRecord.case_id == case_id))
        return list(result.scalars().all())
