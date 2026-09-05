from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from spider.storage.repositories.graph_repo import GraphRepository

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
        for ev in evidence_records:
            evidence_list.append({
                "evidence_id": ev.id,
                "observation_id": ev.observation_id,
                "provider_id": ev.provider_id,
                "upstream_family": ev.upstream_family,
                "confidence_weight": ev.confidence_weight,
                "raw_artifact_sha256": ev.raw_artifact_sha256,
                "timestamp": ev.created_at.isoformat() if ev.created_at else None
            })

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
            "first_observed": asrt.first_observed.isoformat() if asrt.first_observed else None,
            "last_observed": asrt.last_observed.isoformat() if asrt.last_observed else None,
            "evidence_count": len(evidence_list),
            "evidence": evidence_list
        }
