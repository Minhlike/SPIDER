from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from sqlalchemy import delete, select
from spider.service.service import SpiderService
from spider.storage.schema import CaseRecord, TargetRecord, ObservationRecord, EntityRecord, AssertionRecord, EvidenceRefRecord, TaskRunRecord, ProviderRunRecord, ExecutionLedgerRecord

router = APIRouter(prefix="/cases", tags=["Cases"])
from spider.service.review import EvidenceReview, save_review

def get_srv(request: Request) -> SpiderService:
    from spider.web.app import get_service
    return get_service(request)


@router.get("/{case_id}/digest")
async def digest(case_id: str, target_id: str, question: str = "all",
                 limit: int = Query(default=20, ge=1, le=100), after: Optional[str] = None,
                 service: SpiderService = Depends(get_srv)):
    from spider.service.digest import case_digest
    async with service.db_manager.session_factory() as session:
        try:
            return await case_digest(session, case_id, target_id, question, limit, after)
        except ValueError:
            raise HTTPException(422, "Invalid digest scope or cursor") from None

class CreateCaseRequest(BaseModel):
    name: str
    description: Optional[str] = None
    tags: Optional[List[str]] = None


@router.post("/{case_id}/evidence-review")
async def annotate_evidence(case_id: str, review: EvidenceReview, service: SpiderService = Depends(get_srv)):
    if not service.is_running:
        await service.start()
    try:
        return await service.db_writer.submit(lambda session: save_review(session, case_id, review))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

@router.get("", response_model=List[Dict[str, Any]])
async def list_cases(service: SpiderService = Depends(get_srv)):
    is_temp = False
    if not service.is_running:
        await service.start()
        is_temp = True
    try:
        cases = await service.list_cases()
        return cases
    finally:
        if is_temp:
            await service.stop()

@router.post("", response_model=Dict[str, Any])
async def create_case(req: CreateCaseRequest, service: SpiderService = Depends(get_srv)):
    is_temp = False
    if not service.is_running:
        await service.start()
        is_temp = True
    try:
        case = await service.create_case(name=req.name, description=req.description, tags=req.tags)
        return case
    finally:
        if is_temp:
            await service.stop()

@router.get("/{case_id}", response_model=Dict[str, Any])
async def get_case(case_id: str, service: SpiderService = Depends(get_srv)):
    is_temp = False
    if not service.is_running:
        await service.start()
        is_temp = True
    try:
        async with service.db_manager.session_factory() as session:
            case_rec = await session.get(CaseRecord, case_id)
            if not case_rec:
                raise HTTPException(status_code=404, detail="Case not found")
            
            targets_res = await session.execute(select(TargetRecord).where(TargetRecord.case_id == case_id))
            targets = [{"id": t.id, "type": t.observable_type, "value": t.canonical_value, "scope_authorized": t.scope_authorized} for t in targets_res.scalars().all()]
            
            entities = await service.get_case_entities(case_id)
            assertions = await service.get_case_assertions(case_id)
            summary = await service.get_graph_summary(case_id)
            
            return {
                "id": case_rec.id,
                "name": case_rec.name,
                "description": case_rec.description,
                "tags": case_rec.tags or [],
                "status": case_rec.status,
                "created_at": case_rec.created_at.isoformat() if case_rec.created_at else "",
                "targets": targets,
                "entities_count": len(entities),
                "assertions_count": len(assertions),
                "summary": summary
            }
    finally:
        if is_temp:
            await service.stop()

@router.delete("/{case_id}")
async def delete_case(case_id: str, service: SpiderService = Depends(get_srv)):
    is_temp = False
    if not service.is_running:
        await service.start()
        is_temp = True
    try:
        async def _delete_txn(session):
            case_rec = await session.get(CaseRecord, case_id)
            if not case_rec:
                raise HTTPException(status_code=404, detail="Case not found")
            
            await session.execute(delete(EvidenceRefRecord).where(EvidenceRefRecord.assertion_id.in_(
                select(AssertionRecord.id).where(AssertionRecord.case_id == case_id)
            )))
            await session.execute(delete(AssertionRecord).where(AssertionRecord.case_id == case_id))
            await session.execute(delete(EntityRecord).where(EntityRecord.case_id == case_id))
            await session.execute(delete(ObservationRecord).where(ObservationRecord.case_id == case_id))
            await session.execute(delete(TaskRunRecord).where(TaskRunRecord.case_id == case_id))
            await session.execute(delete(ProviderRunRecord).where(ProviderRunRecord.case_id == case_id))
            await session.execute(delete(ExecutionLedgerRecord).where(ExecutionLedgerRecord.case_id == case_id))
            await session.execute(delete(TargetRecord).where(TargetRecord.case_id == case_id))
            await session.execute(delete(CaseRecord).where(CaseRecord.id == case_id))
            return {"status": "DELETED", "case_id": case_id}

        return await service.db_writer.submit(_delete_txn)
    finally:
        if is_temp:
            await service.stop()

@router.get("/{case_id}/export")
async def export_case(case_id: str, target_id: Optional[str] = None, question: str = "all", service: SpiderService = Depends(get_srv)):
    is_temp = False
    if not service.is_running:
        await service.start()
        is_temp = True
    try:
        from spider.service.bundle import evidence_bundle
        async with service.db_manager.session_factory() as session:
            try:
                bundle = await evidence_bundle(session, case_id, target_id, question)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from None
        return {"case_id": case_id, "summary": {"manifest_sha256": bundle["manifest_sha256"]},
                **bundle["manifest"]}
    finally:
        if is_temp:
            await service.stop()


@router.get("/{case_id}/insights", response_model=Dict[str, Any])
async def get_case_insights(case_id: str, target_id: Optional[str] = None, question: str = "all", service: SpiderService = Depends(get_srv)):
    from spider.service.insights import CaseInsightsBuilder
    if not service.is_running:
        await service.start()
    async with service.db_manager.session_factory() as session:
        case_rec = await session.get(CaseRecord, case_id)
        if not case_rec:
            raise HTTPException(status_code=404, detail="Case not found")
        try:
            return await CaseInsightsBuilder.build_insights(session, case_id, case_rec, target_id, question)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/{case_id}/egress")
async def get_egress(case_id: str, target_id: Optional[str] = None, service: SpiderService = Depends(get_srv)):
    from spider.storage.schema import EgressRecord
    async with service.db_manager.session_factory() as session:
        if await session.get(CaseRecord, case_id) is None:
            raise HTTPException(status_code=404, detail="Case not found")
        stmt = select(EgressRecord).where(EgressRecord.case_id == case_id)
        if target_id:
            stmt = stmt.where(EgressRecord.seed_id == target_id)
        rows = list((await session.scalars(stmt.order_by(EgressRecord.observed_at))).all())
        runs = list((await session.scalars(select(ProviderRunRecord).where(ProviderRunRecord.case_id == case_id))).all())
        # Historical runs without instrumentation cannot be called local-only.
        complete = all((r.metadata_json or {}).get("egress_instrumented") for r in runs)
        return {"case_id": case_id, "state": "EGRESS_ATTEMPTED" if rows else "LOCAL_ONLY" if complete else "NOT_YET_VERIFIED",
            "events": [{column.name: getattr(r, column.name) for column in EgressRecord.__table__.columns} for r in rows]}


@router.get("/{case_id}/bundle")
async def get_bundle(case_id: str, target_id: Optional[str] = None, question: str = "all", service: SpiderService = Depends(get_srv)):
    from spider.service.bundle import evidence_bundle
    from fastapi.responses import JSONResponse
    async with service.db_manager.session_factory() as session:
        if await session.get(CaseRecord, case_id) is None:
            raise HTTPException(status_code=404, detail="Case not found")
        try:
            bundle = await evidence_bundle(session, case_id, target_id, question)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return JSONResponse(bundle, headers={"Content-Disposition": 'attachment; filename="spider-evidence.json"'})


@router.get("/{case_id}/entities")
async def get_entities(case_id: str, target_id: Optional[str] = None, question: str = "all", scoped: bool = False, service: SpiderService = Depends(get_srv)):
    entities = await service.get_case_entities(case_id)
    from spider.service.projection import project
    async with service.db_manager.session_factory() as session:
        try:
            view = await project(session, case_id, target_id, question)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
    # Findings never include the query supplied by the user. It remains an
    # internal lineage root and can still anchor the graph view.
    ids = {e.id for e in view.finding_entities}
    entities = [e for e in entities if e["id"] in ids]
    return entities


@router.get("/{case_id}/assertions")
async def get_assertions(case_id: str, target_id: Optional[str] = None, question: str = "all", scoped: bool = False, service: SpiderService = Depends(get_srv)):
    assertions = await service.get_case_assertions(case_id)
    if scoped or target_id:
        from spider.service.projection import project
        async with service.db_manager.session_factory() as session:
            try:
                view = await project(session, case_id, target_id, question)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from None
        by_id = {a.id: a for a in view.assertions}
        assertions = [{**a, "confidence": by_id[a["id"]].confidence, "source_families": by_id[a["id"]].source_families,
                       "independent_source_count": 0} for a in assertions if a["id"] in by_id]
    return assertions


@router.get("/{case_id}/observations")
async def get_observations(case_id: str, target_id: Optional[str] = None, question: str = "all", scoped: bool = False, service: SpiderService = Depends(get_srv)):
    async with service.db_manager.session_factory() as session:
        if await session.get(CaseRecord, case_id) is None:
            raise HTTPException(status_code=404, detail="Case not found")
        observations = (await session.execute(select(ObservationRecord).where(
            ObservationRecord.case_id == case_id
        ).order_by(ObservationRecord.created_at))).scalars().all()
        from spider.service.projection import project
        try:
            observations = (await project(session, case_id, target_id, question)).evidence_observations
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return [{
            "id": obs.id, "case_id": obs.case_id, "run_id": obs.run_id, "task_id": obs.task_id,
            "observable_type": obs.observable_type, "observable_value": obs.observable_value,
            "canonical_value": obs.canonical_value, "provider_id": obs.provider_id,
            "namespace": obs.namespace, "parent_observable_type": obs.parent_observable_type,
            "parent_namespace": obs.parent_namespace, "parent_observable_value": obs.parent_observable_value,
            "upstream_source": obs.upstream_source, "upstream_family": obs.upstream_family,
            "confidence": obs.confidence, "raw_data": obs.raw_data_json,
            "raw_artifact_id": obs.raw_artifact_id, "created_at": obs.created_at.isoformat(),
        } for obs in observations]


@router.get("/{case_id}/report")
async def readable_report(case_id: str, target_id: Optional[str] = None, question: str = "all",
                          language: str = Query(default="vi", pattern="^(vi|en)$"),
                          service: SpiderService = Depends(get_srv)):
    from fastapi.responses import PlainTextResponse
    from spider.service.reporting import markdown_report
    insights = await get_case_insights(case_id, target_id, question, service)
    if insights["scope"]["selection_required"]:
        raise HTTPException(status_code=422, detail="Select a target before exporting a report")
    return PlainTextResponse(markdown_report(insights["reader_report"][language]),
        media_type="text/markdown", headers={"Content-Disposition": 'attachment; filename="spider-report.md"'})
