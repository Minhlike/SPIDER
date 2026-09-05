"""Seed-scoped evidence reachability. Shared entities never transfer another seed's claims."""
from dataclasses import dataclass
from types import SimpleNamespace
from sqlalchemy import select, func
from spider.storage.schema import TargetRecord, EntityRecord, ObservationRecord, AssertionRecord, EvidenceRefRecord

QUESTIONS = {"all", "public_profiles", "infrastructure"}
PROFILE_TYPES = {"EMAIL", "USERNAME", "ACCOUNT", "URL"}


@dataclass
class Projection:
    seed: object
    targets: list
    entities: list
    observations: list
    assertions: list
    excluded_unscoped: int

    @property
    def evidence_observations(self):
        """Collected evidence only; the user-supplied seed is lineage metadata."""
        return [o for o in self.observations if o.provider_id != "seed_target"]

    @property
    def finding_entities(self):
        """Derived entities only; do not present the query itself as a finding."""
        if self.seed is None:
            return self.entities
        root = (self.seed.observable_type, self.seed.namespace, self.seed.canonical_value)
        return [e for e in self.entities
                if (e.observable_type, e.namespace, e.canonical_name) != root]


async def project(session, case_id, target_id=None, question="all"):
    if question not in QUESTIONS:
        raise ValueError("Unsupported question")
    targets = list((await session.scalars(select(TargetRecord).where(TargetRecord.case_id == case_id)
                                         .order_by(TargetRecord.created_at, TargetRecord.id))).all())
    if target_id:
        seed = next((t for t in targets if t.id == target_id), None)
        if seed is None:
            raise ValueError("Target does not belong to this case")
    elif len(targets) == 1:
        seed = targets[0]
    else:
        seed = None
    if seed is None:
        count = await session.scalar(select(func.count()).select_from(ObservationRecord)
                                     .where(ObservationRecord.case_id == case_id))
        return Projection(None, targets, [], [], [], count)
    root = (seed.observable_type, seed.namespace, seed.canonical_value)
    candidates = list((await session.scalars(select(ObservationRecord).where(
        ObservationRecord.case_id == case_id, ObservationRecord.seed_id == seed.id)
        .order_by(ObservationRecord.created_at, ObservationRecord.id))).all())
    unscoped = await session.scalar(select(func.count()).select_from(ObservationRecord).where(
        ObservationRecord.case_id == case_id, ObservationRecord.seed_id.is_(None)))
    reachable, accepted = {root}, {}
    while True:
        before = len(accepted)
        for o in candidates:
            key = (o.observable_type, o.namespace, o.canonical_value)
            parent = (o.parent_observable_type, o.parent_namespace, o.parent_observable_value)
            if (o.provider_id == "seed_target" and key == root) or parent in reachable:
                accepted[o.id] = o
                reachable.add(key)
        if len(accepted) == before:
            break
    observations = list(accepted.values())
    if question != "all":
        def relevant(typ):
            return typ in PROFILE_TYPES if question == "public_profiles" else typ not in {"ACCOUNT", "USERNAME", "URL"}
        observations = [o for o in observations if relevant(o.observable_type)]
    keys = {root} | {(o.observable_type, o.namespace, o.canonical_value) for o in observations}
    entities = [e for e in (await session.scalars(select(EntityRecord).where(EntityRecord.case_id == case_id))).all()
                if (e.observable_type, e.namespace, e.canonical_name) in keys]
    ids = {e.id for e in entities}
    obs_ids = [o.id for o in observations]
    assertions = list((await session.scalars(select(AssertionRecord).where(AssertionRecord.case_id == case_id,
        AssertionRecord.id.in_(select(EvidenceRefRecord.assertion_id).where(EvidenceRefRecord.observation_id.in_(obs_ids))),
        AssertionRecord.source_entity_id.in_(ids), AssertionRecord.target_entity_id.in_(ids)))).all())
    refs = list((await session.scalars(select(EvidenceRefRecord).where(EvidenceRefRecord.observation_id.in_(obs_ids)))).all())
    scoped_assertions = []
    for assertion in assertions:
        evidence = [r for r in refs if r.assertion_id == assertion.id]
        data = {c.name: getattr(assertion, c.name) for c in AssertionRecord.__table__.columns}
        data.update(confidence=max((r.confidence_weight for r in evidence), default=0),
                    source_families=sorted({r.upstream_family for r in evidence}), independent_source_count=0)
        scoped_assertions.append(SimpleNamespace(**data))
    return Projection(seed, targets, entities, observations, scoped_assertions, unscoped)
