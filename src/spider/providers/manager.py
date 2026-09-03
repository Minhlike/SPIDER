import asyncio
import time
from spider.models.base import utc_now
from spider.storage.schema import TaskRunRecord
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

class ProviderManager:
    def __init__(self, artifact_repo: ArtifactRepository, ingest_queue: IngestQueue, db_writer: SingleDBWriter):
        self.adapters: Dict[str, BaseProviderAdapter] = {}
        self.artifact_repo = artifact_repo
        self.ingest_queue = ingest_queue
        self.db_writer = db_writer

    def register_adapter(self, adapter: BaseProviderAdapter) -> None:
        self.adapters[adapter.provider_id()] = adapter

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
                    message=f"Health check failed: {str(e)}"
                )
        return results

    async def execute_task(
        self,
        task: TaskRun,
        target: NormalizedObservable,
        lineage: SourceLineage,
        timeout_seconds: float = 60.0,
        **options
    ) -> ProviderExecutionResult:
        adapter = self.get_adapter(task.provider_id)
        if not adapter:
            raise ValueError(f"Provider {task.provider_id} not registered")

        task.started_at = utc_now()
        started = time.perf_counter()
        await self.db_writer.submit(lambda session: ExecutionRepository.create_task_run(session, task))

        async def on_progress(coverage):
            async def record(session):
                rec = await session.get(TaskRunRecord, task.id)
                rec.metadata_json = {"coverage": coverage, "duration_ms": (time.perf_counter()-started)*1000}
            await self.db_writer.submit(record)

        # Give adapters the same budget; a small grace period allows worker cleanup.
        try:
            result = await asyncio.wait_for(
                adapter.execute(target, lineage, timeout_seconds=timeout_seconds,
                                on_progress=on_progress, **options),
                timeout=timeout_seconds + 2
            )
        except asyncio.TimeoutError:
            result = ProviderExecutionResult(raw_content=b"Execution timed out", observations=[],
                exit_code=124, error_message="Task execution timed out", outcome="FAILED")
        except asyncio.CancelledError:
            async def cancel(session):
                rec = await session.get(TaskRunRecord, task.id)
                rec.status = "CANCELLED"
                rec.completed_at = utc_now()
            await self.db_writer.submit(cancel)
            raise
        except Exception:
            result = ProviderExecutionResult(raw_content=b"Provider execution failed", observations=[],
                exit_code=1, error_message="Provider execution failed", outcome="FAILED")

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
        await self.ingest_queue.ingest_batch(result.observations, artifact)

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
            rec.metadata_json = dict(result.metadata, duration_ms=(time.perf_counter()-started)*1000)
            if not await ExecutionRepository.has_executed(session, task.case_id, task.execution_key_hash):
                await ExecutionRepository.mark_executed(session, task.case_id, task.execution_key_hash, task.status.value)

        await self.db_writer.submit(_record_task)

        return result
