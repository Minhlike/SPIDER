from typing import List, Dict, Tuple, Optional
import uuid
import json
from sqlalchemy.ext.asyncio import AsyncSession
from spider.models.observation import Observation
from spider.models.entity import Entity
from spider.models.assertion import Assertion
from spider.models.evidence import EvidenceRef
from spider.models.enums import ObservableType, AssertionType
from spider.storage.repositories.graph_repo import GraphRepository
from spider.resolution.rules import resolve_assertion_rule

class EntityResolutionEngine:
    def __init__(self, resolver_version: str = "2.1.0"):
        self.resolver_version = resolver_version

    async def resolve_observations(self, session: AsyncSession, observations: List[Observation], case_id: str) -> Tuple[List[Entity], List[Assertion]]:
        entities_created: Dict[str, Entity] = {}
        assertions_created: Dict[str, Assertion] = {}
        resolved = []

        if any(obs.lineage.case_id != case_id for obs in observations):
            raise ValueError("Observation case does not match resolution scope")

        for obs in observations:
            # 1. Resolve / Upsert Entity for the observable
            obs_type = obs.observable.type
            canonical = obs.observable.canonical_value
            
            entity = Entity(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps((case_id, *obs.observable.identity)))),
                case_id=case_id,
                type=obs_type,
                namespace=obs.observable.namespace,
                canonical_name=canonical,
                first_seen=obs.created_at,
                last_seen=obs.created_at,
                metadata=obs.observable.metadata
            )
            entity_rec = await GraphRepository.upsert_entity(session, entity)
            if entity_rec.id == entity.id:
                entities_created[entity.id] = entity
            resolved.append((obs, entity_rec))
            await session.flush()

        # Resolve edges after all entities, independent of provider output order.
        for obs, entity_rec in resolved:
            target_entity_id = entity_rec.id
            obs_type = obs.observable.type
            parent_val = obs.lineage.parent_observable_value
            parent_type = obs.lineage.parent_observable_type
            # Historical untyped references are unknown; never guess from the string.
            if parent_val and parent_type:
                parent_entity_rec = await GraphRepository.get_entity_by_canonical(
                    session, case_id, parent_val, parent_type, obs.lineage.parent_namespace)
                if parent_entity_rec and parent_entity_rec.id != target_entity_id:
                    source_entity_id = parent_entity_rec.id
                    source_type = ObservableType(parent_entity_rec.observable_type)
                    
                    rule = resolve_assertion_rule(source_type, obs_type)
                    asrt_type = rule.assertion_type
                    if asrt_type:
                        assertion = Assertion(
                            id=str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps((case_id, source_entity_id, target_entity_id, asrt_type.value)))),
                            case_id=case_id,
                            source_entity_id=source_entity_id,
                            target_entity_id=target_entity_id,
                            assertion_type=asrt_type,
                            confidence=obs.confidence,
                            independent_source_count=0,
                            source_families=[obs.lineage.upstream_family],
                            resolver_version=self.resolver_version,
                            inference_rule=rule.rule_id,
                            metadata={"rule_version": rule.rule_version,
                                      "rule_registry_version": rule.registry_version,
                                      "evidence_requirement": rule.evidence_requirement},
                            first_observed=obs.created_at,
                            last_observed=obs.created_at
                        )
                        asrt_rec = await GraphRepository.upsert_assertion(session, assertion)
                        if asrt_rec.id == assertion.id:
                            assertions_created[assertion.id] = assertion
                        await session.flush()

                        # Create EvidenceRef
                        evidence = EvidenceRef(
                            assertion_id=asrt_rec.id,
                            observation_id=obs.id,
                            provider_id=obs.lineage.provider_id,
                            upstream_family=obs.lineage.upstream_family,
                            confidence_weight=obs.confidence,
                            raw_artifact_sha256=obs.lineage.raw_artifact_sha256,
                            timestamp=obs.created_at
                        )
                        await GraphRepository.add_evidence_ref(session, evidence)

        return list(entities_created.values()), list(assertions_created.values())
