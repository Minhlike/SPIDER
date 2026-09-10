from typing import Dict, Any, Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from spider.storage.repositories.graph_repo import GraphRepository
from spider.storage.schema import EvidenceReviewRecord, ObservationRecord

class ExplainEngine:
    """
    First-class explanation engine tracing assertions back to independent
    evidence items, upstream source families, and cryptographic raw artifacts.
    """
    @staticmethod
    async def explain_assertion(session: AsyncSession, assertion_id: str) -> Optional[Dict[str, Any]]:
        asrt = await GraphRepository.get_assertion_by_id(session, assertion_id)
        if not asrt:
            return None

        src_entity = await GraphRepository.get_entity_by_id(session, asrt.source_entity_id)
        tgt_entity = await GraphRepository.get_entity_by_id(session, asrt.target_entity_id)
        evidence_records = await GraphRepository.get_evidence_for_assertion(session, assertion_id)

        evidence_list = []
        for ev in sorted(evidence_records, key=lambda row: (
                row.created_at.isoformat() if row.created_at else "", row.id)):
            evidence_list.append({
                "evidence_id": ev.id,
                "observation_id": ev.observation_id,
                "provider_id": ev.provider_id,
                "upstream_family": ev.upstream_family,
                "confidence_weight": ev.confidence_weight,
                "raw_artifact_sha256": ev.raw_artifact_sha256,
                "timestamp": ev.created_at.isoformat() if ev.created_at else None
            })

        reviews = list((await session.scalars(select(EvidenceReviewRecord).where(
            EvidenceReviewRecord.case_id == asrt.case_id,
            EvidenceReviewRecord.claim_id == assertion_id))).all())
        reviews.sort(key=lambda row: (
            row.reviewed_at.isoformat() if row.reviewed_at else "", row.id))
        reviewed_ids = {review.observation_id for review in reviews}
        reviewed_observations = list((await session.scalars(select(ObservationRecord).where(
            ObservationRecord.id.in_(reviewed_ids)))).all()) if reviewed_ids else []
        observed_by_id = {row.id: row for row in reviewed_observations}
        rule_metadata = asrt.metadata_json if isinstance(asrt.metadata_json, dict) else {}
        rule_node = f"rule:{asrt.inference_rule}:{rule_metadata.get('rule_version') or 'legacy'}"
        claim_node = f"claim:{asrt.id}"
        nodes = [{"id": claim_node, "kind": "CLAIM", "assertion_type": asrt.assertion_type},
                 {"id": rule_node, "kind": "RULE", "rule_id": asrt.inference_rule,
                  "version": rule_metadata.get("rule_version"),
                  "registry_version": rule_metadata.get("rule_registry_version"),
                  "evidence_requirement": rule_metadata.get("evidence_requirement")}]
        edges = [{"from": rule_node, "to": claim_node, "kind": "DERIVES"}]
        known_evidence = set()
        for evidence in evidence_list:
            node_id = f"evidence:{evidence['observation_id']}"
            known_evidence.add(evidence["observation_id"])
            nodes.append({"id": node_id, "kind": "EVIDENCE",
                          "observation_id": evidence["observation_id"],
                          "provider_id": evidence["provider_id"],
                          "observed_at": evidence["timestamp"],
                          "artifact_sha256": evidence["raw_artifact_sha256"]})
            edges.append({"from": node_id, "to": rule_node, "kind": "SATISFIES_REQUIREMENT"})
        for review in reviews:
            node_id = f"evidence:{review.observation_id}"
            if review.observation_id not in known_evidence:
                observation = observed_by_id.get(review.observation_id)
                if observation is None:
                    continue
                nodes.append({"id": node_id, "kind": "EVIDENCE",
                              "observation_id": observation.id,
                              "provider_id": observation.provider_id,
                              "observed_at": observation.created_at.isoformat(),
                              "artifact_sha256": observation.raw_artifact_sha256})
                known_evidence.add(review.observation_id)
            edge_kind = {"SUPPORTING_EVIDENCE": "SUPPORTS",
                         "CONTRADICTING_EVIDENCE": "CONTRADICTS",
                         "UNKNOWN": "RELEVANCE_UNKNOWN"}[review.role]
            edges.append({"from": node_id, "to": claim_node, "kind": edge_kind,
                          "dependency": review.dependency,
                          "origin_id": review.origin_id})
        contradictory = sum(review.role == "CONTRADICTING_EVIDENCE" for review in reviews)
        unknown = sum(review.role == "UNKNOWN" for review in reviews)
        candidate_relation = asrt.assertion_type in {
            "SHARES_USERNAME", "POSSIBLY_SAME_IDENTITY", "ASSOCIATED_WITH"}
        lifecycle = ("CONTESTED" if contradictory else "REVIEW_REQUIRED"
                     if unknown or candidate_relation else "SUPPORTED_RELATION")

        from spider.service.reporting import evidence_note
        return {
            "reader_note": {lang: evidence_note(lang) for lang in ("vi", "en")},
            "assertion_id": asrt.id,
            "source_entity": {
                "id": src_entity.id if src_entity else asrt.source_entity_id,
                "canonical_name": src_entity.canonical_name if src_entity else "UNKNOWN",
                "type": src_entity.observable_type if src_entity else "UNKNOWN"
            },
            "target_entity": {
                "id": tgt_entity.id if tgt_entity else asrt.target_entity_id,
                "canonical_name": tgt_entity.canonical_name if tgt_entity else "UNKNOWN",
                "type": tgt_entity.observable_type if tgt_entity else "UNKNOWN"
            },
            "assertion_type": asrt.assertion_type,
            "confidence": asrt.confidence,
            "independent_source_count": asrt.independent_source_count,
            "source_families": asrt.source_families or [],
            "resolver_version": asrt.resolver_version,
            "inference_rule": asrt.inference_rule,
            "rule": {"id": asrt.inference_rule,
                     "version": rule_metadata.get("rule_version"),
                     "registry_version": rule_metadata.get("rule_registry_version"),
                     "evidence_requirement": rule_metadata.get("evidence_requirement")},
            "claim_lifecycle": {"state": lifecycle, "identity_verified": False,
                                "supporting_evidence": len(evidence_list) + sum(
                                    review.role == "SUPPORTING_EVIDENCE" for review in reviews),
                                "contradicting_evidence": contradictory,
                                "unknown_relevance": unknown},
            "justification_dag": {"schema_version": "1", "acyclic": True,
                                  "proof_complete": bool(evidence_list and rule_metadata.get("rule_version")),
                                  "nodes": nodes, "edges": edges},
            "first_observed": asrt.first_observed.isoformat() if asrt.first_observed else None,
            "last_observed": asrt.last_observed.isoformat() if asrt.last_observed else None,
            "evidence_count": len(evidence_list),
            "evidence": evidence_list
        }
