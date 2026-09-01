from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from spider.storage.schema import ObservationRecord
from spider.models.observation import Observation

class ObservationRepository:
    @staticmethod
    async def append_observation(session: AsyncSession, obs: Observation) -> ObservationRecord:
        record = ObservationRecord(
            id=obs.id,
            case_id=obs.lineage.case_id,
            run_id=obs.lineage.run_id,
            task_id=obs.lineage.task_id,
            observable_type=obs.observable.type.value,
            observable_value=obs.observable.value,
            canonical_value=obs.observable.canonical_value,
            provider_id=obs.lineage.provider_id,
            provider_version=obs.lineage.provider_version,
            adapter_version=obs.lineage.adapter_version,
            upstream_source=obs.lineage.upstream_source,
            upstream_family=obs.lineage.upstream_family,
            parent_observable_value=obs.lineage.parent_observable_value,
            configuration_hash=obs.lineage.configuration_hash,
            confidence=obs.confidence,
            raw_data_json=obs.raw_data,
            raw_artifact_id=obs.raw_artifact_id,
            created_at=obs.created_at
        )
        session.add(record)
        return record

    @staticmethod
    async def append_observations_batch(session: AsyncSession, observations: List[Observation]) -> List[ObservationRecord]:
        records = []
        for obs in observations:
            rec = ObservationRecord(
                id=obs.id,
                case_id=obs.lineage.case_id,
                run_id=obs.lineage.run_id,
                task_id=obs.lineage.task_id,
                observable_type=obs.observable.type.value,
                observable_value=obs.observable.value,
                canonical_value=obs.observable.canonical_value,
                provider_id=obs.lineage.provider_id,
                provider_version=obs.lineage.provider_version,
                adapter_version=obs.lineage.adapter_version,
                upstream_source=obs.lineage.upstream_source,
                upstream_family=obs.lineage.upstream_family,
                parent_observable_value=obs.lineage.parent_observable_value,
                configuration_hash=obs.lineage.configuration_hash,
                confidence=obs.confidence,
                raw_data_json=obs.raw_data,
                raw_artifact_id=obs.raw_artifact_id,
                created_at=obs.created_at
            )
            session.add(rec)
            records.append(rec)
        return records

    @staticmethod
    async def get_observations_for_case(session: AsyncSession, case_id: str) -> List[ObservationRecord]:
        result = await session.execute(
            select(ObservationRecord).where(ObservationRecord.case_id == case_id).order_by(ObservationRecord.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_observations_by_canonical(session: AsyncSession, case_id: str, canonical_value: str) -> List[ObservationRecord]:
        result = await session.execute(
            select(ObservationRecord).where(
                ObservationRecord.case_id == case_id,
                ObservationRecord.canonical_value == canonical_value
            )
        )
        return list(result.scalars().all())
