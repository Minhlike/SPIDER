"""Reproducible, allowlisted manifest. Never packages raw files, settings or credentials."""
import hashlib
import json
from sqlalchemy import select
from spider.storage.schema import CaseRecord, EvidenceRefRecord, ProviderRunRecord
from spider.service.projection import project
from spider.service.evidence_analysis import analyze, public_url
from spider.service.review import hypotheses


async def evidence_bundle(session, case_id, target_id=None, question="all"):
    view = await project(session, case_id, target_id, question)
    if len(view.targets) > 1 and view.seed is None:
        raise ValueError("Select a target before exporting evidence")
    observations = view.evidence_observations
    entities = view.finding_entities
    root_entity = next((entity for entity in view.entities
                        if view.seed and entity.observable_type == view.seed.observable_type
                        and entity.namespace == view.seed.namespace
                        and entity.canonical_name == view.seed.canonical_value), None)
    obs_ids = [o.id for o in observations]
    refs = list((await session.scalars(select(EvidenceRefRecord).where(EvidenceRefRecord.observation_id.in_(obs_ids)))).all())
    runs = list((await session.scalars(select(ProviderRunRecord).where(ProviderRunRecord.case_id == case_id))).all())
    def raw_mapping(observation):
        return observation.raw_data_json if isinstance(observation.raw_data_json, dict) else {}

    payload = {"schema": "spider.evidence-bundle.v1", "case_id": case_id,
        "target_id": view.seed.id if view.seed else None, "question": question,
        "query_context": ({"entity_id": root_entity.id, "type": root_entity.observable_type,
                           "namespace": root_entity.namespace,
                           "canonical_value": root_entity.canonical_name,
                           "evidence": False, "finding": False}
                          if root_entity else None),
        "review_status": "NOT_YET_VERIFIED", "unscoped_excluded": view.excluded_unscoped,
        "entities": [{"id": e.id, "type": e.observable_type, "namespace": e.namespace,
                      "canonical_value": e.canonical_name} for e in sorted(entities, key=lambda e: e.id)],
        "claims": [{"id": a.id, "source": a.source_entity_id, "target": a.target_entity_id,
                    "type": a.assertion_type, "resolver_version": a.resolver_version,
                    "review_status": "NOT_YET_VERIFIED"} for a in sorted(view.assertions, key=lambda a: a.id)],
        "observations": [{"id": o.id, "run_id": o.run_id, "task_id": o.task_id,
            "provider_id": o.provider_id, "provider_version": o.provider_version, "parser_version": o.adapter_version,
            "observed_at": o.created_at.isoformat(), "artifact_sha256": o.raw_artifact_sha256,
            "config_hash": o.configuration_hash, "collection_method": o.upstream_family,
            "source_url": public_url(raw_mapping(o).get("profile_url"))}
            for o in sorted(observations, key=lambda o: o.id)],
        "evidence_refs": [{"claim_id": e.assertion_id, "observation_id": e.observation_id} for e in sorted(refs, key=lambda e: e.id)],
        "runs": [{"id": r.id, "status": r.status, "budget": (r.metadata_json or {}).get("budget_limits"),
                  "ledger": (r.metadata_json or {}).get("budget_ledger")} for r in sorted(runs, key=lambda r: r.id)],
        "analysis": {**analyze(observations), "hypotheses": await hypotheses(session, case_id, view)},
        "included_raw_artifacts": False}
    from spider.service.insights import CaseInsightsBuilder
    case = await session.get(CaseRecord, case_id)
    if case is None:
        raise ValueError("Case not found")
    insights = await CaseInsightsBuilder.build_insights(session, case_id, case, target_id, question)
    payload["reader_report"] = insights["reader_report"]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return {"manifest": payload, "manifest_sha256": hashlib.sha256(encoded).hexdigest()}
