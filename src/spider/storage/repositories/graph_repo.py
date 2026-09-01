from typing import List, Optional, Tuple
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from spider.storage.schema import EntityRecord, AssertionRecord, EvidenceRefRecord
from spider.models.entity import Entity
from spider.models.assertion import Assertion
from spider.models.evidence import EvidenceRef

class GraphRepository:
    @staticmethod
    async def upsert_entity(session: AsyncSession, entity: Entity) -> EntityRecord:
        result = await session.execute(
            select(EntityRecord).where(
                EntityRecord.case_id == entity.case_id,
                EntityRecord.canonical_name == entity.canonical_name
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.last_seen = entity.last_seen
            existing.observation_count += 1
            if entity.metadata:
                existing.metadata_json.update(entity.metadata)
            return existing
        else:
            rec = EntityRecord(
                id=entity.id,
                case_id=entity.case_id,
                observable_type=entity.type.value,
                canonical_name=entity.canonical_name,
                first_seen=entity.first_seen,
                last_seen=entity.last_seen,
                observation_count=entity.observation_count,
                metadata_json=entity.metadata
            )
            session.add(rec)
            return rec

    @staticmethod
    async def get_entities_for_case(session: AsyncSession, case_id: str) -> List[EntityRecord]:
        result = await session.execute(select(EntityRecord).where(EntityRecord.case_id == case_id))
        return list(result.scalars().all())

    @staticmethod
    async def get_entity_by_canonical(session: AsyncSession, case_id: str, canonical_name: str) -> Optional[EntityRecord]:
        result = await session.execute(
            select(EntityRecord).where(
                EntityRecord.case_id == case_id,
                EntityRecord.canonical_name == canonical_name
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_entity_by_id(session: AsyncSession, entity_id: str) -> Optional[EntityRecord]:
        result = await session.execute(select(EntityRecord).where(EntityRecord.id == entity_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_assertion(session: AsyncSession, assertion: Assertion) -> AssertionRecord:
        result = await session.execute(
            select(AssertionRecord).where(
                AssertionRecord.case_id == assertion.case_id,
                AssertionRecord.source_entity_id == assertion.source_entity_id,
                AssertionRecord.target_entity_id == assertion.target_entity_id,
                AssertionRecord.assertion_type == assertion.assertion_type.value
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.last_observed = assertion.last_observed
            existing.confidence = max(existing.confidence, assertion.confidence)
            existing.independent_source_count = max(existing.independent_source_count, assertion.independent_source_count)
            # merge source families
            merged_families = list(set(existing.source_families + assertion.source_families))
            existing.source_families = merged_families
            return existing
        else:
            rec = AssertionRecord(
                id=assertion.id,
                case_id=assertion.case_id,
                source_entity_id=assertion.source_entity_id,
                target_entity_id=assertion.target_entity_id,
                assertion_type=assertion.assertion_type.value,
                confidence=assertion.confidence,
                independent_source_count=assertion.independent_source_count,
                source_families=assertion.source_families,
                resolver_version=assertion.resolver_version,
                inference_rule=assertion.inference_rule,
                first_observed=assertion.first_observed,
                last_observed=assertion.last_observed,
                metadata_json=assertion.metadata
            )
            session.add(rec)
            return rec

    @staticmethod
    async def add_evidence_ref(session: AsyncSession, evidence: EvidenceRef) -> EvidenceRefRecord:
        rec = EvidenceRefRecord(
            id=evidence.id,
            assertion_id=evidence.assertion_id,
            observation_id=evidence.observation_id,
            provider_id=evidence.provider_id,
            upstream_family=evidence.upstream_family,
            confidence_weight=evidence.confidence_weight,
            excerpt=evidence.excerpt,
            raw_artifact_sha256=evidence.raw_artifact_sha256,
            created_at=evidence.timestamp
        )
        session.add(rec)
        return rec

    @staticmethod
    async def get_assertions_for_case(session: AsyncSession, case_id: str) -> List[AssertionRecord]:
        result = await session.execute(select(AssertionRecord).where(AssertionRecord.case_id == case_id))
        return list(result.scalars().all())

    @staticmethod
    async def get_assertion_by_id(session: AsyncSession, assertion_id: str) -> Optional[AssertionRecord]:
        result = await session.execute(select(AssertionRecord).where(AssertionRecord.id == assertion_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_evidence_for_assertion(session: AsyncSession, assertion_id: str) -> List[EvidenceRefRecord]:
        result = await session.execute(select(EvidenceRefRecord).where(EvidenceRefRecord.assertion_id == assertion_id))
        return list(result.scalars().all())

    @staticmethod
    async def clear_case_graph(session: AsyncSession, case_id: str) -> None:
        """Clears materialized graph (entities, assertions, evidence_refs) for a case to allow clean rebuild"""
        assertions = await GraphRepository.get_assertions_for_case(session, case_id)
        assertion_ids = [a.id for a in assertions]
        if assertion_ids:
            await session.execute(delete(EvidenceRefRecord).where(EvidenceRefRecord.assertion_id.in_(assertion_ids)))
        await session.execute(delete(AssertionRecord).where(AssertionRecord.case_id == case_id))
        await session.execute(delete(EntityRecord).where(EntityRecord.case_id == case_id))
