from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from sqlalchemy import delete, select
from spider.service.service import SpiderService
from spider.storage.schema import CaseRecord, TargetRecord, ObservationRecord, EntityRecord, AssertionRecord, EvidenceRefRecord, TaskRunRecord, ProviderRunRecord, ExecutionLedgerRecord

router = APIRouter(prefix="/cases", tags=["Cases"])

def get_srv(request: Request) -> SpiderService:
    from spider.web.app import get_service
    return get_service(request)

class CreateCaseRequest(BaseModel):
    name: str
    description: Optional[str] = None
    tags: Optional[List[str]] = None

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
async def export_case(case_id: str, service: SpiderService = Depends(get_srv)):
    is_temp = False
    if not service.is_running:
        await service.start()
        is_temp = True
    try:
        entities = await service.get_case_entities(case_id)
        assertions = await service.get_case_assertions(case_id)
        summary = await service.get_graph_summary(case_id)
        return {
            "case_id": case_id,
            "summary": summary,
            "entities": entities,
            "assertions": assertions
        }
    finally:
        if is_temp:
            await service.stop()


@router.get("/{case_id}/insights", response_model=Dict[str, Any])
async def get_case_insights(case_id: str, service: SpiderService = Depends(get_srv)):
    from spider.service.insights import CaseInsightsBuilder
    if not service.is_running:
        await service.start()
    async with service.db_manager.session_factory() as session:
        case_rec = await session.get(CaseRecord, case_id)
        if not case_rec:
            raise HTTPException(status_code=404, detail="Case not found")
        return await CaseInsightsBuilder.build_insights(session, case_id, case_rec)
