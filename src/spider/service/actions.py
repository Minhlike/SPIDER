"""Evidence-linked, bounded single-capability actions for an owned service session.

Durable at-most-once admission; uncertain runs are never automatically replayed.
No caller-supplied observable, lineage, credential or arbitrary command is accepted.
"""
import asyncio
import hashlib
import json
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func

from spider.capability.applicability import assess_provider
from spider.capability.scopes import PERSONAL_CAPABILITIES
from spider.models.base import utc_now
from spider.models.budget import BudgetLedger, ExecutionBudget
from spider.models.enums import ObservableType, ExecutionStatus
from spider.models.execution import TaskRun, ExecutionKey
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage
from spider.service.projection import project
from spider.service.reporting import label
from spider.service.review import EvidenceReview, save_review
from spider.storage.schema import InvestigationActionRecord, ProviderRunRecord, TaskRunRecord, ObservationRecord


class ActionError(ValueError):
    """Only fixed codes cross the API boundary."""


class RunCapabilityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: UUID
    target_id: str = Field(min_length=1, max_length=64)
    entity_id: str = Field(min_length=1, max_length=64)
    capability: str = Field(min_length=1, max_length=64)
    provider_id: str = Field(min_length=1, max_length=64)
    observation_id: str | None = Field(default=None, min_length=1, max_length=64)
    question: Literal["all", "public_profiles", "infrastructure"] = "all"
    policy_profile: str = Field(default="passive_standard", max_length=64)
    browser_assisted: bool = False
    max_requests: int = Field(default=20, ge=1, le=100, strict=True)
    max_entities: int = Field(default=20, ge=1, le=100, strict=True)
    timeout_seconds: int = Field(default=60, ge=1, le=120, strict=True)


class CancelRunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: UUID
    target_id: str = Field(min_length=1, max_length=64)
    run_id: str = Field(min_length=1, max_length=64)


class EvidenceAnnotationInput(EvidenceReview):
    model_config = ConfigDict(extra="forbid")
    action_id: UUID
    question: Literal["all", "public_profiles", "infrastructure"] = "all"


def action_key(case_id, action_id):
    return hashlib.sha256(f"{case_id}|{UUID(str(action_id))}".encode()).hexdigest()


class InvestigationActions:
    max_pending = 16

    def __init__(self, service):
        self.service = service
        self._admission = asyncio.Lock()
        # New actions remain serial until the cross-run transport gate passes.
        self._execution = asyncio.Lock()

    def _task(self, run_id):
        return next((t for t in self.service.background_tasks
                     if t.get_name() == f"spider-run:{run_id}" and not t.done()), None)

    def _require_session(self):
        if not self.service.is_running or self.service._stopping:
            raise ActionError("SESSION_REQUIRED")

    async def _validate(self, session, case_id, request):
        view = await project(session, case_id, request.target_id, request.question)
        entity = next((e for e in view.entities if e.id == request.entity_id), None)
        if entity is None or view.seed is None:
            raise ActionError("ENTITY_OUTSIDE_SCOPE")
        identity = (entity.observable_type, entity.namespace, entity.canonical_name)
        root = (view.seed.observable_type, view.seed.namespace, view.seed.canonical_value)
        proof = next((o for o in view.evidence_observations if o.id == request.observation_id), None)
        if request.observation_id is not None or identity != root:
            if proof is None or (proof.observable_type, proof.namespace, proof.canonical_value) != identity:
                raise ActionError("EVIDENCE_LINK_REQUIRED")
        kind = ObservableType(entity.observable_type)
        cap = self.service.capability_registry.get_capability(request.capability)
        adapter = self.service.provider_manager.get_adapter(request.provider_id)
        if (cap is None or kind not in cap.input_types or request.provider_id not in cap.default_providers
                or not assess_provider(adapter, kind, request.capability).applicable):
            raise ActionError("UNSUPPORTED_CAPABILITY")
        if not adapter.request_budget_supported:
            raise ActionError("UNMETERED_PROVIDER")
        personal = request.capability in PERSONAL_CAPABILITIES
        if ((request.question == "public_profiles" and not personal)
                or (request.question == "infrastructure" and personal)):
            raise ActionError("CAPABILITY_OUTSIDE_QUESTION")
        if request.capability == "BROWSER_PERSONAL_DISCOVERY" and not request.browser_assisted:
            raise ActionError("BROWSER_INTENT_REQUIRED")
        if request.policy_profile not in self.service.policy_engine.profiles:
            raise ActionError("UNKNOWN_POLICY")
        # Association never transfers the seed's permission to a derived entity.
        context = self.service.policy_engine.get_context(request.policy_profile,
            is_target_in_scope=identity == root and view.seed.scope_authorized)
        if not context.is_action_allowed(adapter.network_class()):
            raise ActionError("POLICY_DENIED")
        observable = NormalizedObservable(type=kind, namespace=entity.namespace,
            value=entity.canonical_name, canonical_value=entity.canonical_name)
        return observable, identity == root

    async def run_capability(self, case_id, request):
        self._require_session()
        key = action_key(case_id, request.action_id)
        args = request.model_dump(mode="json", exclude={"action_id"})
        digest = hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()
        async with self._admission:
            self._require_session()

            async def admit(session):
                prior = await session.get(InvestigationActionRecord, key)
                if prior:
                    if prior.kind != "RUN_CAPABILITY" or prior.payload_sha256 != digest:
                        raise ActionError("ACTION_ID_CONFLICT")
                    return prior.run_id, None, False
                observable, direct = await self._validate(session, case_id, request)
                pending = sum(not t.done() for t in self.service.background_tasks)
                if pending >= self.max_pending:
                    raise ActionError("ACTION_QUEUE_FULL")
                run_id = str(uuid4())
                session.add(ProviderRunRecord(id=run_id, case_id=case_id, status="QUEUED",
                    metadata_json={"target_ids": [request.target_id], "question": request.question,
                        "expected_sources": {request.target_id: [request.provider_id]},
                        "action_receipt_id": key, "origin_observation_id": request.observation_id,
                        "policy_profile": request.policy_profile, "egress_instrumented": True,
                        "budget_limits": self._budget(request).model_dump(mode="json")}))
                await session.flush()
                session.add(InvestigationActionRecord(id=key, case_id=case_id,
                    seed_id=request.target_id, run_id=run_id, kind="RUN_CAPABILITY",
                    payload_sha256=digest, arguments_json=args))
                return run_id, observable, direct

            run_id, observable, direct = await self.service.db_writer.submit(admit)
            if observable is not None:
                # No awaits between committed admission and registering the owned task.
                task = asyncio.create_task(self._execute(case_id, run_id, key, request, observable, direct),
                                           name=f"spider-run:{run_id}")
                self.service.background_tasks.add(task)
                task.add_done_callback(self.service.background_tasks.discard)
            return await self.status(case_id, request.target_id, request.action_id)

    @staticmethod
    def _budget(request):
        return ExecutionBudget(max_requests=request.max_requests, max_entities=request.max_entities,
            max_runtime_seconds=request.timeout_seconds, max_depth=0, max_parallel_tasks=1,
            max_provider_calls=1)

    async def _finish(self, run_id, state, ledger=None):
        async def write(session):
            run = await session.get(ProviderRunRecord, run_id)
            if run is None:
                return
            if state == "CANCELLED" and run.status in {"COMPLETED", "PARTIAL", "FAILED"}:
                return
            run.status, run.completed_at = state, utc_now()
            tasks = list((await session.scalars(select(TaskRunRecord).where(TaskRunRecord.run_id == run_id))).all())
            for task in tasks:
                if task.status in ("QUEUED", "RUNNING", "PENDING"):
                    task.status, task.completed_at = state, utc_now()
            run.tasks_count = len(tasks)
            run.observations_count = await session.scalar(select(func.count()).select_from(
                ObservationRecord).where(ObservationRecord.run_id == run_id))
            if ledger is not None:
                run.metadata_json = {**(run.metadata_json or {}), "budget_ledger": ledger.model_dump(mode="json")}
        await self.service.db_writer.submit(write)

    async def _execute(self, case_id, run_id, key, request, observable, direct):
        ledger, budget = BudgetLedger(), self._budget(request)
        try:
            async with self._execution:
                # Recheck mutable policy/evidence before any provider I/O.
                async with self.service.db_manager.session_factory() as session:
                    await self._validate(session, case_id, request)
                async def running(session):
                    row = await session.get(ProviderRunRecord, run_id)
                    row.status, row.started_at = "RUNNING", utc_now()
                await self.service.db_writer.submit(running)
                ledger.admit_entity(budget, case_id, observable)
                task = TaskRun(case_id=case_id, run_id=run_id, provider_id=request.provider_id,
                    capability=request.capability, status=ExecutionStatus.RUNNING,
                    target_observable_value=observable.canonical_value,
                    execution_key_hash=ExecutionKey(entity_id=request.entity_id,
                        capability=request.capability, provider_id=request.provider_id,
                        configuration_hash=key).key_string,
                    metadata={"seed_id": request.target_id, "question": request.question,
                        "origin_observation_id": request.observation_id, "action_receipt_id": key,
                        "target_type": observable.type.value, "target_namespace": observable.namespace})
                adapter = self.service.provider_manager.get_adapter(request.provider_id)
                lineage = SourceLineage(case_id=case_id, run_id=run_id, task_id=task.id,
                    provider_id=request.provider_id, provider_version=adapter.version(),
                    adapter_version=adapter.adapter_version(), seed_id=request.target_id,
                    parent_observable_value=observable.canonical_value,
                    parent_observable_type=observable.type, parent_namespace=observable.namespace,
                    configuration_hash=key)
                ledger.provider_calls_count = 1
                result = await self.service.provider_manager.execute_task(task, observable, lineage,
                    timeout_seconds=request.timeout_seconds, request_ledger=ledger, execution_budget=budget,
                    derivation="DIRECT" if direct else "DERIVED",
                    browser_parent_observation_id=request.observation_id,
                    browser_action_id=request.action_id,
                    username_site_limit=budget.username_site_limit,
                    username_source_scope=budget.username_source_scope,
                    resolve_batch=lambda session, observations: self.service.resolution_engine.resolve_observations(
                        session, observations, case_id))
                state = result.outcome or ("COMPLETED" if result.exit_code == 0 else "FAILED")
                await self._finish(run_id, state if state in {"COMPLETED", "PARTIAL", "FAILED"} else "FAILED", ledger)
        except asyncio.CancelledError:
            await self._finish(run_id, "CANCELLED", ledger)
            raise
        except Exception:
            # Never expose provider exception text or target data in a receipt.
            await self._finish(run_id, "FAILED", ledger)

    async def status(self, case_id, target_id, action_id):
        async with self.service.db_manager.session_factory() as session:
            row = await session.get(InvestigationActionRecord, action_key(case_id, action_id))
            if row is None or row.case_id != case_id or row.seed_id != target_id:
                raise ActionError("ACTION_OUTSIDE_SCOPE")
            if row.kind == "ANNOTATE_EVIDENCE":
                return {"receipt_id": row.id, "target_id": row.seed_id,
                        "kind": row.kind, **row.result_json}
            run = await session.get(ProviderRunRecord, row.run_id)
            attached = self._task(run.id) is not None
            state = run.status
            if state in {"QUEUED", "RUNNING"} and not attached:
                state = "UNKNOWN_AFTER_RESTART"
            budget = (run.metadata_json or {}).get("budget_ledger", {})
            return {"receipt_id": row.id, "run_id": run.id, "target_id": row.seed_id,
                "kind": row.kind, "status": state, "task_attached": attached,
                "automatic_replay": False, "identity_verified": False,
                "origin_observation_id": (run.metadata_json or {}).get("origin_observation_id"),
                "tasks_count": run.tasks_count, "observations_count": run.observations_count,
                "requests_count": budget.get("requests_count", 0 if state == "QUEUED" else None),
                "accounting": "LAST_PERSISTED_RECEIPTS",
                "reader_note": {lang: label(state, lang) for lang in ("vi", "en")}}

    async def cancel_run(self, case_id, request):
        self._require_session()
        key = action_key(case_id, request.action_id)
        args = request.model_dump(mode="json", exclude={"action_id"})
        digest = hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()
        async with self._admission:
            self._require_session()
            async def admit(session):
                source = await session.scalar(select(InvestigationActionRecord).where(
                    InvestigationActionRecord.case_id == case_id,
                    InvestigationActionRecord.seed_id == request.target_id,
                    InvestigationActionRecord.run_id == request.run_id,
                    InvestigationActionRecord.kind == "RUN_CAPABILITY"))
                if source is None:
                    raise ActionError("ACTION_OUTSIDE_SCOPE")
                prior = await session.get(InvestigationActionRecord, key)
                if prior:
                    if prior.kind != "CANCEL_RUN" or prior.payload_sha256 != digest:
                        raise ActionError("ACTION_ID_CONFLICT")
                else:
                    session.add(InvestigationActionRecord(id=key, case_id=case_id,
                        seed_id=request.target_id, run_id=request.run_id, kind="CANCEL_RUN",
                        payload_sha256=digest, arguments_json=args))
            await self.service.db_writer.submit(admit)
            task = self._task(request.run_id)
            if task is not None:
                if not task.cancelling():
                    task.cancel()
                await asyncio.shield(asyncio.gather(task, return_exceptions=True))
                # Also handles cancellation before the coroutine's first instruction.
                await self._finish(request.run_id, "CANCELLED")
            return await self.status(case_id, request.target_id, request.action_id)

    async def annotate_evidence(self, case_id, request):
        key = action_key(case_id, request.action_id)
        args = request.model_dump(mode="json", exclude={"action_id"})
        digest = hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()
        async def write(session):
            prior = await session.get(InvestigationActionRecord, key)
            if prior:
                if prior.kind != "ANNOTATE_EVIDENCE" or prior.payload_sha256 != digest:
                    raise ActionError("ACTION_ID_CONFLICT")
                return
            view = await project(session, case_id, request.target_id, request.question)
            if (request.claim_id not in {a.id for a in view.assertions}
                    or request.observation_id not in {o.id for o in view.evidence_observations}
                    or (request.origin_id and request.origin_id not in {o.id for o in view.evidence_observations})):
                raise ActionError("EVIDENCE_OUTSIDE_QUESTION")
            review = EvidenceReview.model_validate({k: v for k, v in args.items() if k != "question"})
            result = await save_review(session, case_id, review)
            result["reader_note"] = {lang: label("REVIEW_REQUIRED", lang) for lang in ("vi", "en")}
            session.add(InvestigationActionRecord(id=key, case_id=case_id, seed_id=request.target_id,
                kind="ANNOTATE_EVIDENCE", arguments_json=args, payload_sha256=digest, result_json=result))
        await self.service.db_writer.submit(write)
        return await self.status(case_id, request.target_id, request.action_id)
