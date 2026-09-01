import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional
from spider.service.service import SpiderService
from spider.models.classifier import TargetClassifier
from spider.models.budget import ExecutionBudget
from spider.web.events import event_broker

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

async def _run_investigation_background(service: SpiderService, case_id: str, target: str, obs_type_val: str, budget: ExecutionBudget, profile: Optional[str]):
    await event_broker.broadcast("RUN_STARTED", {
        "case_id": case_id,
        "target": target,
        "type": obs_type_val,
        "policy_profile": profile
    })
    try:
        run_res = await service.investigate(
            case_id=case_id,
            budget=budget,
            policy_profile=profile
        )
        entities = await service.get_case_entities(case_id)
        assertions = await service.get_case_assertions(case_id)
        await event_broker.broadcast("RUN_COMPLETED", {
            "case_id": case_id,
            "run_result": run_res,
            "entities_count": len(entities),
            "assertions_count": len(assertions)
        })
    except Exception as e:
        await event_broker.broadcast("RUN_FAILED", {
            "case_id": case_id,
            "error": str(e)
        })

@router.post("/investigate", response_model=Dict[str, Any])
async def start_investigation(
    req: StartInvestigationRequest,
    background_tasks: BackgroundTasks,
    service: SpiderService = Depends(get_srv)
):
    is_temp = False
    if not service.db_manager:
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

        # Dispatch background investigation non-blockingly
        background_tasks.add_task(
            _run_investigation_background,
            service,
            case_id,
            req.target,
            obs_type.value,
            budget,
            req.policy_profile
        )

        return {
            "case_id": case_id,
            "target": req.target,
            "type": obs_type.value,
            "status": "QUEUED",
            "message": "Investigation queued and running in background"
        }
    finally:
        if is_temp:
            pass # Keep alive for background tasks
