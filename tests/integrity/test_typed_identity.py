import pytest
from sqlalchemy import select
from spider.models.case import Case
from spider.models.enums import ObservableType as T
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage
from spider.storage.database import DatabaseManager
from spider.storage.repositories.case_repo import CaseRepository
from spider.storage.repositories.graph_repo import GraphRepository
from spider.storage.repositories.observation_repo import ObservationRepository
from spider.storage.schema import EvidenceRefRecord
from spider.resolution.resolver import EntityResolutionEngine
from spider.resolution.rebuilder import KnowledgeGraphRebuilder


def observation(typ, value, namespace="", parent=None, case="case"):
    lineage = SourceLineage(case_id=case, run_id="run", task_id="task", provider_id="fixture",
                            provider_version="1", raw_artifact_sha256="a" * 64)
    if parent:
        lineage = lineage.with_parent(parent[1], parent[0], parent[2] if len(parent) > 2 else "")
    return Observation(observable=NormalizedObservable(type=typ, value=value, namespace=namespace,
                       metadata={"fixture": True}), lineage=lineage)


@pytest.mark.asyncio
async def test_types_namespaces_lineage_and_rebuild_remain_separate(tmp_path):
    db = DatabaseManager(str(tmp_path / "typed.db"))
    await db.initialize()
    try:
        async with db.session_factory.begin() as session:
            await CaseRepository.create_case(session, Case(id="case", name="Synthetic identities"))
            await session.flush()
            # Children intentionally precede their typed parents.
            observations = [observation(T.IP_ADDRESS, "192.0.2.1", parent=(T.DOMAIN, "alice.dev")),
                observation(T.ACCOUNT, "alice", "github", (T.USERNAME, "alice.dev")),
                observation(T.ACCOUNT, "alice", "gitlab", (T.USERNAME, "alice.dev")),
                observation(T.DOMAIN, "alice.dev"), observation(T.USERNAME, "alice.dev")]
            await ObservationRepository.append_observations_batch(session, observations)
            await session.flush()
            entities, _ = await EntityResolutionEngine().resolve_observations(session, observations, "case")
            assert len(entities) == 5
        for rebuild in (False, True, True):
            async with db.session_factory.begin() as session:
                if rebuild:
                    await KnowledgeGraphRebuilder().rebuild_case(session, "case")
                entities = await GraphRepository.get_entities_for_case(session, "case")
                by_id = {e.id: (e.observable_type, e.namespace, e.canonical_name) for e in entities}
                assert len(by_id) == 5
                assert all(e.metadata_json == {"fixture": True} for e in entities)
                assertions = await GraphRepository.get_assertions_for_case(session, "case")
                assert len(assertions) == 3
                for edge in assertions:
                    parent, child = by_id[edge.source_entity_id], by_id[edge.target_entity_id]
                    assert parent[0] == ("DOMAIN" if child[0] == "IP_ADDRESS" else "USERNAME")
                evidence = (await session.execute(select(EvidenceRefRecord))).scalars().all()
                assert len(evidence) == 3 and all(e.raw_artifact_sha256 == "a" * 64 for e in evidence)
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_unknown_parent_and_foreign_case_never_attach(tmp_path):
    db = DatabaseManager(str(tmp_path / "scope.db"))
    await db.initialize()
    try:
        async with db.session_factory.begin() as session:
            await CaseRepository.create_case(session, Case(id="case", name="Scope"))
            await session.flush()
            obs = observation(T.IP_ADDRESS, "192.0.2.1")
            obs.lineage.parent_observable_value = "alice.dev"  # legacy, type unknown
            await ObservationRepository.append_observations_batch(session, [obs])
            await session.flush()
            resolver = EntityResolutionEngine()
            await resolver.resolve_observations(session, [observation(T.DOMAIN, "alice.dev"), obs], "case")
            assert not await GraphRepository.get_assertions_for_case(session, "case")
            with pytest.raises(ValueError, match="case"):
                await resolver.resolve_observations(session, [observation(T.DOMAIN, "other.test", case="foreign")], "case")
    finally:
        await db.close()


def test_legacy_adapter_cannot_inherit_wrong_parent_type():
    old = observation(T.DOMAIN, "example.test", parent=(T.EMAIL, "fixture@example.test")).lineage
    changed = old.model_copy(update={"parent_observable_value": "example.test"})
    assert changed.parent_observable_type is None
    assert old.parent_observable_type == T.EMAIL
