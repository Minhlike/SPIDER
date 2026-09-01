from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, Optional
from spider.cli.main import get_service, infer_observable_type
from spider.models.budget import ExecutionBudget
from spider.web.events import event_broker

router = APIRouter(tags=["Investigation"])

class StartInvestigationRequest(BaseModel):
    target: str
    case_id: Optional[str] = None
    case_name: Optional[str] = None
    authorized_scope: bool = False
    max_depth: int = 2
    policy_profile: Optional[str] = "passive_standard"

@router.post("/investigate", response_model=Dict[str, Any])
async def start_investigation(req: StartInvestigationRequest):
    service = get_service()
    await service.start()
    try:
        case_id = req.case_id
        if not case_id:
            name = req.case_name or f"Investigation: {req.target}"
            case_res = await service.create_case(name=name, tags=["web_ui"])
            case_id = case_res["id"]

        obs_type = infer_observable_type(req.target)
        await service.add_target(
            case_id=case_id,
            raw_input=req.target,
            observable_type=obs_type,
            scope_authorized=req.authorized_scope
        )

        await event_broker.broadcast("RUN_STARTED", {
            "case_id": case_id,
            "target": req.target,
            "type": obs_type.value,
            "policy_profile": req.policy_profile
        })

        budget = ExecutionBudget(max_depth=req.max_depth)
        run_res = await service.investigate(
            case_id=case_id,
            budget=budget,
            policy_profile=req.policy_profile
        )

        await event_broker.broadcast("RUN_COMPLETED", {
            "case_id": case_id,
            "run_result": run_res
        })

        entities = await service.get_case_entities(case_id)
        assertions = await service.get_case_assertions(case_id)

        return {
            "case_id": case_id,
            "target": req.target,
            "type": obs_type.value,
            "run_result": run_res,
            "entities_count": len(entities),
            "assertions_count": len(assertions)
        }
    finally:
        await service.stop()

@router.post("/cases/{case_id}/rebuild", response_model=Dict[str, Any])
async def rebuild_case(case_id: str):
    service = get_service()
    await service.start()
    try:
        res = await service.rebuild_case(case_id)
        await event_broker.broadcast("GRAPH_REBUILT", {
            "case_id": case_id,
            "rebuild_result": res
        })
        return res
    finally:
        await service.stop()
