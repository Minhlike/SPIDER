import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from spider.storage.repositories.observation_repo import ObservationRepository
from spider.storage.repositories.graph_repo import GraphRepository
from spider.resolution.resolver import EntityResolutionEngine
from spider.models.observation import Observation
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage
from spider.models.enums import ObservableType

logger = logging.getLogger(__name__)

class KnowledgeGraphRebuilder:
    def __init__(self, resolver: Optional[EntityResolutionEngine] = None):
        self.resolver = resolver or EntityResolutionEngine()

    async def rebuild_case(self, session: AsyncSession, case_id: str) -> Dict[str, Any]:
        """
        Rebuilds the entire materialized Knowledge Graph (entities, assertions, evidence)
        for a case from the append-only observation log.
        Zero network queries.
        """
        # 1. Fetch all raw observations in chronological order
        obs_records = await ObservationRepository.get_observations_for_case(session, case_id)
        if not obs_records:
            return {"status": "NO_OBSERVATIONS", "entities_count": 0, "assertions_count": 0}

        # 2. Clear current materialized graph for this case
        await GraphRepository.clear_case_graph(session, case_id)

        # 3. Convert records to domain Observation models
        observations = []
        for rec in obs_records:
            obs = Observation(
                id=rec.id,
                observable=NormalizedObservable(
                    type=ObservableType(rec.observable_type),
                    value=rec.observable_value,
                    namespace=rec.namespace,
                    metadata=rec.observable_metadata or {},
                    canonical_value=rec.canonical_value
                ),
                lineage=SourceLineage(
                    case_id=rec.case_id,
                    run_id=rec.run_id,
                    task_id=rec.task_id,
                    seed_id=rec.seed_id,
                    provider_id=rec.provider_id,
                    provider_version=rec.provider_version,
                    adapter_version=rec.adapter_version,
                    upstream_source=rec.upstream_source,
                    upstream_family=rec.upstream_family,
                    parent_observable_value=rec.parent_observable_value,
                    parent_observable_type=rec.parent_observable_type,
                    parent_namespace=rec.parent_namespace,
                    configuration_hash=rec.configuration_hash,
                    raw_artifact_sha256=rec.raw_artifact_sha256,
                    timestamp=rec.created_at
                ),
                confidence=rec.confidence,
                raw_data=rec.raw_data_json or {},
                raw_artifact_id=rec.raw_artifact_id,
                created_at=rec.created_at
            )
            observations.append(obs)

        # 4. Re-run resolution engine
        await self.resolver.resolve_observations(session, observations, case_id)

        # 5. Query rebuilt counts
        entities = await GraphRepository.get_entities_for_case(session, case_id)
        assertions = await GraphRepository.get_assertions_for_case(session, case_id)

        return {
            "status": "SUCCESS",
            "observations_processed": len(observations),
            "entities_rebuilt": len(entities),
            "assertions_rebuilt": len(assertions)
        }
