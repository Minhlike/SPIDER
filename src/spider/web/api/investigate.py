import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional
from spider.service.service import SpiderService
from spider.models.classifier import TargetClassifier
from spider.models.budget import ExecutionBudget
from spider.web.events import event_broker
from spider.models.execution import ProviderRun
from spider.models.enums import ExecutionStatus
from spider.storage.repositories.execution_repo import ExecutionRepository
from spider.storage.schema import ProviderRunRecord
from spider.models.base import utc_now

router = APIRouter(tags=["Investigation"])

def get_srv(request: Request) -> SpiderService:
    from spider.web.app import get_service
    return get_service(request)

class StartInvestigationRequest(BaseModel):
    target: str
    case_id: Optional[str] = None
    case_name: Optional[str] = None
    authorized_scope: bool = False
    max_depth: int = 2
    policy_profile: Optional[str] = "passive_standard"

async def _run_investigation_background(service: SpiderService, case_id: str, run_id: str, target: str, obs_type_val: str, budget: ExecutionBudget, profile: Optional[str]):
    await event_broker.broadcast("RUN_STARTED", {
        "case_id": case_id,
        "run_id": run_id,
        "target": target,
        "type": obs_type_val,
        "policy_profile": profile
    })
    try:
        run_res = await service.investigate(
            case_id=case_id,
            budget=budget,
            policy_profile=profile,
            run_id=run_id
        )
        entities = await service.get_case_entities(case_id)
        assertions = await service.get_case_assertions(case_id)
        await event_broker.broadcast("RUN_COMPLETED", {
            "case_id": case_id,
            "run_result": run_res,
            "entities_count": len(entities),
            "assertions_count": len(assertions)
        })
    except asyncio.CancelledError:
        await _finish_interrupted_run(service, run_id, "CANCELLED")
        raise
    except Exception:
        await _finish_interrupted_run(service, run_id, "FAILED")
        await event_broker.broadcast("RUN_FAILED", {
            "case_id": case_id,
            "error": "Investigation failed"
        })


async def _finish_interrupted_run(service, run_id, status):
    async def update(session):
        run = await session.get(ProviderRunRecord, run_id)
        if run:
            run.status = status
            run.completed_at = utc_now()
    await service.db_writer.submit(update)

@router.post("/investigate", response_model=Dict[str, Any])
async def start_investigation(
    req: StartInvestigationRequest,
    background_tasks: BackgroundTasks,
    service: SpiderService = Depends(get_srv)
):
    is_temp = False
    if not service.is_running:
        await service.start()
        is_temp = True

    try:
        case_id = req.case_id
        if not case_id:
            name = req.case_name or f"Investigation: {req.target}"
            case_res = await service.create_case(name=name, tags=["web_ui"])
            case_id = case_res["id"]

        classification = TargetClassifier.classify(req.target)
        obs_type = classification.detected_type
        await service.add_target(
            case_id=case_id,
            raw_input=req.target,
            observable_type=obs_type,
            scope_authorized=req.authorized_scope
        )

        budget = ExecutionBudget(max_depth=req.max_depth)

        import uuid
        run_id = str(uuid.uuid4())

        async def queue_run(session):
            await ExecutionRepository.create_provider_run(session, ProviderRun(
                id=run_id, case_id=case_id, status=ExecutionStatus.QUEUED
            ))
        await service.db_writer.submit(queue_run)

        # Dispatch true background task on event loop
        task = asyncio.create_task(
            _run_investigation_background(
                service,
                case_id,
                run_id,
                req.target,
                obs_type.value,
                budget,
                req.policy_profile
            ),
            name=f"spider-run:{run_id}",
        )
        service.background_tasks.add(task)
        task.add_done_callback(service.background_tasks.discard)

        return {
            "case_id": case_id,
            "run_id": run_id,
            "target": req.target,
            "type": obs_type.value,
            "status": "QUEUED",
            "message": "Investigation queued and running in background"
        }
    finally:
        if is_temp:
            pass # Keep alive for background tasks
