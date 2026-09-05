from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any, Optional
from pathlib import Path
from spider.service.service import SpiderService

router = APIRouter(prefix="/explain", tags=["Explain & Evidence"])

def get_srv(request: Request) -> SpiderService:
    from spider.web.app import get_service
    return get_service(request)


@router.get("")
async def explain_entity(case_id: str, entity_id: str, target_id: Optional[str] = None, service: SpiderService = Depends(get_srv)):
    from sqlalchemy import select
    from spider.storage.schema import EntityRecord, ObservationRecord
    async with service.db_manager.session_factory() as session:
        entity = await session.get(EntityRecord, entity_id)
        if not entity or entity.case_id != case_id:
            raise HTTPException(status_code=404, detail="Entity not found in case")
        from spider.service.projection import project
        from spider.service.reporting import evidence_note
        try:
            view = await project(session, case_id, target_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid target scope") from None
        if view.seed is None:
            raise HTTPException(status_code=422, detail="Select a target")
        if entity_id not in {item.id for item in view.entities}:
            raise HTTPException(status_code=404, detail="Entity outside selected target")
        matched = [o for o in view.evidence_observations if
                   (o.observable_type, o.namespace, o.canonical_value) ==
                   (entity.observable_type, entity.namespace, entity.canonical_name)]
        observations = matched[:300]
        return {
            "reader_note": {lang: evidence_note(lang) for lang in ("vi", "en")},
            "truncated": len(matched) > 300,
            "entity": {"id": entity.id, "type": entity.observable_type,
                       "canonical_name": entity.canonical_name, "observation_count": entity.observation_count,
                       "first_seen": entity.first_seen.isoformat()},
            "provenance_chain": [{"provider_id": obs.provider_id, "upstream_source": obs.upstream_source,
                                  "upstream_family": obs.upstream_family, "task_id": obs.task_id,
                                  "confidence": obs.confidence, "raw_artifact_id": obs.raw_artifact_id}
                                 for obs in observations],
        }

@router.get("/{assertion_id}", response_model=Dict[str, Any])
async def explain_assertion(assertion_id: str, service: SpiderService = Depends(get_srv)):
    is_temp = False
    if not service.is_running:
        await service.start()
        is_temp = True
    try:
        explanation = await service.explain_assertion(assertion_id)
        if not explanation:
            raise HTTPException(status_code=404, detail="Assertion not found")
        return explanation
    finally:
        if is_temp:
            await service.stop()

@router.get("/artifact/{artifact_sha256}")
async def view_raw_artifact(artifact_sha256: str):
    runs_dir = Path("data/runs")
    for raw_file in runs_dir.glob("*/*.raw"):
        if artifact_sha256[:8] in raw_file.name:
            content = raw_file.read_text(encoding="utf-8", errors="replace")
            preview = content[:50000]
            return {
                "file_name": raw_file.name,
                "sha256": artifact_sha256,
                "byte_size": raw_file.stat().st_size,
                "content_preview": preview
            }
    raise HTTPException(status_code=404, detail="Artifact file not found on disk")
