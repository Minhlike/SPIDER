import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field, AliasChoices
from typing import Dict, Any, Optional, Literal
from spider.service.service import SpiderService
from spider.models.classifier import TargetClassifier, ClassificationError
from spider.models.budget import ExecutionBudget
from spider.web.events import event_broker
from spider.models.execution import ProviderRun
from spider.models.enums import ExecutionStatus, ObservableType
from spider.storage.repositories.execution_repo import ExecutionRepository
from spider.storage.schema import ProviderRunRecord
from spider.models.base import utc_now
from spider.capability.scopes import resolve_investigation_mode
from spider.service.resume import prepare_resume, ResumeError

router = APIRouter(tags=["Investigation"])

def get_srv(request: Request) -> SpiderService:
    from spider.web.app import get_service
    return get_service(request)

class InvestigationBudgetRequest(BaseModel):
    max_depth: int = Field(default=1, ge=0, le=3)
    max_entities: int = Field(default=500, ge=1, le=5000)
    max_requests: Optional[int] = Field(default=100, ge=0, le=5000)
    timeout_seconds: Optional[int] = Field(default=180, ge=10, le=86400)
    username_site_limit: Literal[0, 50, 500] = 500
    username_source_scope: Literal["VN_COMMON_CORE", "GLOBAL_50", "GLOBAL_500", "GLOBAL_ALL"] = "VN_COMMON_CORE"

class StartInvestigationRequest(BaseModel):
    target: str = Field(min_length=1, max_length=2048)
    target_type: Optional[ObservableType] = None
    case_id: Optional[str] = None
    case_name: Optional[str] = None
    authorized_scope: bool = Field(default=False, validation_alias=AliasChoices("authorized_scope", "scope_authorized"))
    max_depth: int = Field(default=2, ge=0, le=3)
    budget: Optional[InvestigationBudgetRequest] = None
    policy_profile: Optional[str] = "passive_standard"
    investigation_mode: Literal["AUTO", "PERSONAL_FOOTPRINT", "INFRASTRUCTURE"] = "AUTO"
    browser_assisted: bool = False


class ResumeInvestigationRequest(BaseModel):
    budget: Optional[InvestigationBudgetRequest] = None

async def _run_investigation_background(service: SpiderService, case_id: str, run_id: str,
                                        target: str, obs_type_val: str, budget: ExecutionBudget,
                                        profile: Optional[str], investigation_mode: str,
                                        browser_assisted: bool,
                                        resume_from_run_id: Optional[str] = None):
    await event_broker.broadcast("RUN_STARTED", {
        "case_id": case_id,
        "run_id": run_id,
        "target": target,
        "type": obs_type_val,
        "policy_profile": profile,
        "investigation_mode": investigation_mode,
        "browser_assisted": browser_assisted,
    })
    try:
        options = dict(
            case_id=case_id,
            budget=budget,
            policy_profile=profile,
            run_id=run_id,
            investigation_mode=investigation_mode,
            browser_assisted=browser_assisted,
        )
        if resume_from_run_id is not None:
            options["resume_from_run_id"] = resume_from_run_id
        run_res = await service.investigate(**options)
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
        await _broadcast_cancelled_run(service, case_id, run_id)
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


async def _broadcast_cancelled_run(service: SpiderService, case_id: str, run_id: str) -> None:
    entities = await service.get_case_entities(case_id)
    assertions = await service.get_case_assertions(case_id)
    await event_broker.broadcast("RUN_COMPLETED", {
        "case_id": case_id,
        "run_result": {"run_id": run_id, "status": "CANCELLED"},
        "entities_count": len(entities),
        "assertions_count": len(assertions),
    })


@router.post("/runs/{run_id}/stop", response_model=Dict[str, Any])
async def stop_investigation_run(run_id: str, service: SpiderService = Depends(get_srv)):
    async with service.db_manager.session_factory() as session:
        run = await session.get(ProviderRunRecord, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail={
                "code": "run_not_found", "message": "Investigation run was not found",
            })
        case_id, status = run.case_id, run.status
    if status in {"COMPLETED", "PARTIAL", "FAILED", "CANCELLED"}:
        return {"run_id": run_id, "case_id": case_id, "status": status}

    task = next((item for item in service.background_tasks
                 if item.get_name() == f"spider-run:{run_id}"), None)
    if task is None:
        raise HTTPException(status_code=409, detail={
            "code": "run_not_owned_by_process",
            "message": "The run is not attached to this SPIDER process; it was not stopped",
        })
    if not task.cancelling():
        task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    async with service.db_manager.session_factory() as session:
        run = await session.get(ProviderRunRecord, run_id)
        status = run.status if run else "CANCELLED"
    if status not in {"CANCELLED", "COMPLETED", "PARTIAL", "FAILED"}:
        await _finish_interrupted_run(service, run_id, "CANCELLED")
        status = "CANCELLED"
        await _broadcast_cancelled_run(service, case_id, run_id)
    return {"run_id": run_id, "case_id": case_id, "status": status}


@router.post("/runs/{run_id}/resume", response_model=Dict[str, Any])
async def resume_investigation_run(run_id: str, req: ResumeInvestigationRequest,
                                   service: SpiderService = Depends(get_srv)):
    budget = None
    if req.budget:
        budget = ExecutionBudget(
            max_depth=req.budget.max_depth, max_entities=req.budget.max_entities,
            max_requests=req.budget.max_requests,
            max_runtime_seconds=req.budget.timeout_seconds,
            max_provider_calls=None if req.budget.max_requests is None else 50,
            username_site_limit=req.budget.username_site_limit,
            username_source_scope=req.budget.username_source_scope)
    try:
        spec = await prepare_resume(service, run_id, budget=budget)
    except ResumeError as exc:
        status_code = 404 if str(exc) == "RUN_NOT_FOUND" else 409
        raise HTTPException(status_code=status_code, detail={
            "code": str(exc).lower(), "message": "This run cannot be resumed",
        }) from None
    task = asyncio.create_task(_run_investigation_background(
        service, spec.case_id, spec.run_id, spec.target, spec.observable_type,
        spec.budget, spec.policy_profile, spec.investigation_mode,
        spec.browser_assisted, spec.source_run_id),
        name=f"spider-run:{spec.run_id}")
    service.background_tasks.add(task)
    task.add_done_callback(service.background_tasks.discard)
    return {"case_id": spec.case_id, "run_id": spec.run_id,
            "resumed_from_run_id": spec.source_run_id, "status": "QUEUED"}

@router.post("/investigate", response_model=Dict[str, Any])
async def start_investigation(
    req: StartInvestigationRequest,
    background_tasks: BackgroundTasks,
    service: SpiderService = Depends(get_srv)
):
    try:
        classification = TargetClassifier.resolve(req.target, req.target_type)
    except ClassificationError as exc:
        raise HTTPException(status_code=422, detail=exc.detail()) from None
    try:
        investigation_mode = resolve_investigation_mode(
            [classification.detected_type], req.investigation_mode
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "incompatible_investigation_mode",
            "message": str(exc),
        }) from None
    if req.browser_assisted and investigation_mode.value != "PERSONAL_FOOTPRINT":
        raise HTTPException(status_code=422, detail={
            "code": "browser_mode_requires_personal_target",
            "message": "Cốc Cốc assisted discovery only supports EMAIL or USERNAME targets",
        })
    if req.browser_assisted and not req.authorized_scope:
        raise HTTPException(status_code=422, detail={
            "code": "browser_scope_authorization_required",
            "message": "Confirm authorized scope before using the signed-in browser session",
        })
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

        obs_type = classification.detected_type
        await service.add_target(
            case_id=case_id,
            raw_input=req.target,
            observable_type=obs_type,
            scope_authorized=req.authorized_scope,
            canonical_value=classification.canonical_value,
            metadata={
                "classification": classification.model_dump(mode="json"),
                "investigation_mode": investigation_mode.value,
            }
        )

        budget = (ExecutionBudget(max_depth=req.budget.max_depth,
                    max_entities=req.budget.max_entities,
                    max_requests=req.budget.max_requests,
                    max_runtime_seconds=req.budget.timeout_seconds,
                    max_provider_calls=None if req.budget.max_requests is None else 50,
                    username_site_limit=req.budget.username_site_limit,
                    username_source_scope=req.budget.username_source_scope)
                  if req.budget else ExecutionBudget(max_depth=req.max_depth))

        import uuid
        run_id = str(uuid.uuid4())

        async def queue_run(session):
            from spider.storage.repositories.case_repo import CaseRepository
            queued_targets = await CaseRepository.get_targets(session, case_id)
            await ExecutionRepository.create_provider_run(session, ProviderRun(
                id=run_id, case_id=case_id, status=ExecutionStatus.QUEUED,
                metadata={"target_ids": [target.id for target in queued_targets]}
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
                req.policy_profile,
                investigation_mode.value,
                req.browser_assisted,
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
            "investigation_mode": investigation_mode.value,
            "browser_assisted": req.browser_assisted,
            "status": "QUEUED",
            "message": "Investigation queued and running in background"
        }
    finally:
        if is_temp:
            pass # Keep alive for background tasks
