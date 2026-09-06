import asyncio
import time
from contextlib import nullcontext
from spider.models.base import utc_now
from spider.storage.schema import TaskRunRecord, ProviderAuditRecord
from typing import Dict, List, Optional
from spider.providers.base import BaseProviderAdapter, ProviderHealth, ProviderExecutionResult
from spider.models.enums import ObservableType, NetworkClass, ProviderState, ExecutionStatus
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage
from spider.models.execution import TaskRun
from spider.models.raw_artifact import RawArtifactRef
from spider.storage.repositories.artifact_repo import ArtifactRepository
from spider.ingest.queue import IngestQueue
from spider.storage.writer import SingleDBWriter
from spider.storage.repositories.execution_repo import ExecutionRepository
from spider.models.budget import RequestBudgetExceeded
from spider.service.egress import EgressRecorder
from spider.providers.limits import OriginLimits
from spider.providers.http_plane import HTTPPlane

class ProviderManager:
    def __init__(self, artifact_repo: ArtifactRepository, ingest_queue: IngestQueue, db_writer: SingleDBWriter):
        self.adapters: Dict[str, BaseProviderAdapter] = {}
        self._global_slots = asyncio.Semaphore(4)
        self._provider_slots = {}
        self.origin_limits = OriginLimits()
        self.http_plane = HTTPPlane()
        self.artifact_repo = artifact_repo
        self.ingest_queue = ingest_queue
        self.db_writer = db_writer

    def register_adapter(self, adapter: BaseProviderAdapter) -> None:
        self.adapters[adapter.provider_id()] = adapter
        self._provider_slots.setdefault(adapter.provider_id(), asyncio.Semaphore(1))

    def get_adapter(self, provider_id: str) -> Optional[BaseProviderAdapter]:
        return self.adapters.get(provider_id)

    def list_adapters(self) -> List[BaseProviderAdapter]:
        return list(self.adapters.values())

    def get_provider_network_classes(self) -> Dict[str, NetworkClass]:
        return {pid: a.network_class() for pid, a in self.adapters.items()}

    async def check_all_health(self) -> Dict[str, ProviderHealth]:
        results = {}
        for pid, adapter in self.adapters.items():
            try:
                results[pid] = await adapter.health()
            except Exception as e:
                results[pid] = ProviderHealth(
                    state=ProviderState.BROKEN,
                    message="Provider health check failed"
                )
            if self.db_writer._running:
                from datetime import timezone
                async with self.db_writer.db_manager.session_factory() as session:
                    audit = await session.get(ProviderAuditRecord, pid)
                if audit:
                    health = results[pid]
                    health.details["canary_state"] = audit.state
                    if audit.state == "QUARANTINED":
                        health.state = ProviderState.QUARANTINED
                        health.message = "Provider quarantined after canary failures"
                    elif audit.state == "CONTRACT_PASSED" and (audit.provider_version, audit.adapter_version) == (adapter.version(), adapter.adapter_version()):
                        payload = health.model_dump()
                        payload.update(provider_version=adapter.version(), adapter_version=adapter.adapter_version(), contract_verified=True,
                            verification_evidence={"contract": {"provider_version": audit.provider_version,
                                "adapter_version": audit.adapter_version, "checked_at": audit.checked_at.replace(tzinfo=timezone.utc),
                                "artifact_sha256": audit.report_sha256}})
                        results[pid] = ProviderHealth.model_validate(payload)
        return results

    async def execute_task(self, task, target, lineage, timeout_seconds=60.0, **options):
        try:
            return await self._execute_task(task, target, lineage, timeout_seconds, **options)
        except asyncio.CancelledError:
            async def cancel(session):
                rec = await session.get(TaskRunRecord, task.id)
                if rec and rec.status in ("PENDING", "QUEUED", "RUNNING"):
                    rec.status, rec.completed_at = "CANCELLED", utc_now()
            await self.db_writer.submit(cancel)
            raise

    async def _execute_task(
        self,
        task: TaskRun,
        target: NormalizedObservable,
        lineage: SourceLineage,
        timeout_seconds: float = 60.0,
        **options
    ) -> ProviderExecutionResult:
        adapter = self.get_adapter(task.provider_id)
        resolve_batch = options.pop("resolve_batch", None)
        commit_order = options.pop("commit_order", None)
        commit_index = options.pop("commit_index", 0)
        options["origin_limits"] = self.origin_limits
        options["http_plane"] = self.http_plane
        options["http_run_scope"] = (task.run_id, adapter.adapter_version()) if adapter else None
        if not adapter:
            raise ValueError(f"Provider {task.provider_id} not registered")

        task.started_at = utc_now()
        started = time.perf_counter()
        task.metadata.update(provider_version=adapter.version(), adapter_version=adapter.adapter_version())
        await self.db_writer.submit(lambda session: ExecutionRepository.create_task_run(session, task))
        ledger = options.get("request_ledger")
        task_ledger = ledger.for_task(task.id) if ledger is not None else None
        starting_request_count = task_ledger.attributed_requests_count if task_ledger is not None else 0
        if ledger is not None:
            options["request_ledger"] = task_ledger
            options["egress_recorder"] = EgressRecorder(self.db_writer, task, target, lineage,
                options.pop("derivation", "DERIVED"), ledger._fingerprint_salt)

        async def persist_budget():
            if ledger is not None:
                from spider.storage.schema import ProviderRunRecord
                async def write(session):
                    rec = await session.get(ProviderRunRecord, task.run_id)
                    if rec:
                        rec.metadata_json = {**(rec.metadata_json or {}), "budget_ledger": ledger.model_dump(mode="json")}
                await self.db_writer.submit(write)

        async def on_progress(coverage):
            async def record(session):
                rec = await session.get(TaskRunRecord, task.id)
                rec.metadata_json = {**task.metadata, "coverage": coverage, "duration_ms": (time.perf_counter()-started)*1000}
            await self.db_writer.submit(record)
            await persist_budget()

        # Give adapters the same budget; a small grace period allows worker cleanup.
        try:
            async with self.db_writer.db_manager.session_factory() as session:
                audit = await session.get(ProviderAuditRecord, task.provider_id)
            if audit and audit.state == "QUARANTINED":
                result = ProviderExecutionResult(raw_content=b"", observations=[], outcome="PARTIAL",
                    error_message="Provider quarantined after canary failures", metadata={"budget_reason": "QUARANTINED"})
            elif options.get("request_ledger") is not None and not adapter.request_budget_supported:
                result = ProviderExecutionResult(raw_content=b"", observations=[], outcome="PARTIAL",
                    error_message="Provider blocked: network request accounting unavailable",
                    metadata={"budget_reason": "UNMETERED_PROVIDER"})
            else:
                async def dispatch():
                    queued = time.perf_counter()
                    async with self._provider_slots[task.provider_id], self._global_slots:
                        entered = time.perf_counter()
                        task.metadata["provider_wait_ms"] = (entered - queued) * 1000
                        try:
                            return await adapter.execute(target, lineage, timeout_seconds=timeout_seconds,
                                                         on_progress=on_progress, **options)
                        finally:
                            task.metadata["provider_execution_ms"] = (time.perf_counter() - entered) * 1000
                result = await asyncio.wait_for(dispatch(), timeout=timeout_seconds + 2)
        except RequestBudgetExceeded:
            result = ProviderExecutionResult(raw_content=b"", observations=[], outcome="PARTIAL",
                error_message="Network request budget exhausted", metadata={"budget_reason": "REQUEST_LIMIT"})
        except asyncio.TimeoutError:
            result = ProviderExecutionResult(raw_content=b"Execution timed out", observations=[],
                exit_code=124, error_message="Task execution timed out", outcome="FAILED", metadata={"collection_state": "TIMEOUT"})
        except asyncio.CancelledError:
            async def cancel(session):
                rec = await session.get(TaskRunRecord, task.id)
                rec.status = "CANCELLED"
                rec.completed_at = utc_now()
                rec.metadata_json = {**task.metadata, "duration_ms": (time.perf_counter()-started)*1000,
                    "request_count": task_ledger.attributed_requests_count - starting_request_count
                    if task_ledger is not None else None}
            await self.db_writer.submit(cancel)
            raise
        except Exception:
            result = ProviderExecutionResult(raw_content=b"Provider execution failed", observations=[],
                exit_code=1, error_message="Provider execution failed", outcome="FAILED")
        finally:
            await persist_budget()

        commit_started = time.perf_counter()
        async with commit_order.slot(commit_index) if commit_order else nullcontext():
            task.metadata["commit_wait_ms"] = (time.perf_counter() - commit_started) * 1000
            ledger, budget = options.get("request_ledger"), options.get("execution_budget")
            if any((obs.lineage.case_id, obs.lineage.run_id, obs.lineage.task_id,
                    obs.lineage.provider_id, obs.lineage.seed_id) !=
                   (task.case_id, task.run_id, task.id, task.provider_id, lineage.seed_id)
                   for obs in result.observations):
                result = ProviderExecutionResult(raw_content=b"", observations=[], outcome="FAILED",
                                                 error_message="Observation scope mismatch")
            if ledger is not None:
                accepted = [obs for obs in result.observations if ledger.admit_entity(budget, task.case_id, obs.observable)]
                dropped = len(result.observations) - len(accepted)
                result.observations = accepted
                if dropped:
                    result.outcome = "PARTIAL"
                    result.metadata.update(budget_reason="ENTITY_LIMIT", budget_dropped=dropped)
                    result.error_message = "Entity budget exhausted; partial results retained"

            if task_ledger is not None:
                result.metadata["request_count"] = task_ledger.attributed_requests_count - starting_request_count
                result.metadata["cache_hits_count"] = task_ledger.attributed_cache_hits_count
                if task_ledger.attributed_cache_hits_count:
                    result.metadata["source_freshness"] = "SOME_RESPONSES_REPLAYED_WITHIN_RUN"

            # Store raw artifact to disk with SHA-256
            artifact = self.artifact_repo.store_raw_bytes(
                case_id=task.case_id,
                run_id=task.run_id,
                task_id=task.id,
                provider_id=task.provider_id,
                content=result.raw_content,
                mime_type=result.mime_type
            )
            task.raw_artifact_id = artifact.id

            # Attach raw_artifact_id and sha256 to observations
            for obs in result.observations:
                obs.raw_artifact_id = artifact.id
                obs.lineage.raw_artifact_sha256 = artifact.sha256

            # Ingest to DB
            if resolve_batch is None:
                await self.ingest_queue.ingest_batch(result.observations, artifact)
            else:
                await self.ingest_queue.ingest_batch(result.observations, artifact, resolve_batch=resolve_batch)

            # Record ledger
            async def _record_task(session):
                task.observations_count = len(result.observations)
                task.status = ExecutionStatus(result.outcome) if result.outcome else (ExecutionStatus.COMPLETED if result.exit_code == 0 else ExecutionStatus.FAILED)
                rec = await session.get(TaskRunRecord, task.id)
                rec.status = task.status.value
                rec.observations_count = task.observations_count
                rec.raw_artifact_id = task.raw_artifact_id
                rec.completed_at = utc_now()
                rec.error_message = result.error_message
                rec.metadata_json = dict(task.metadata, **result.metadata, duration_ms=(time.perf_counter()-started)*1000)
                if not await ExecutionRepository.has_executed(session, task.case_id, task.execution_key_hash):
                    await ExecutionRepository.mark_executed(session, task.case_id, task.execution_key_hash, task.status.value)

            await self.db_writer.submit(_record_task)

            return result
