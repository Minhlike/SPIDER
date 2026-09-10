import asyncio
from typing import List, Dict, Any, Optional
from spider.storage.database import DatabaseManager
from spider.storage.writer import SingleDBWriter
from spider.storage.repositories.case_repo import CaseRepository
from spider.storage.repositories.graph_repo import GraphRepository
from spider.storage.repositories.observation_repo import ObservationRepository
from spider.storage.repositories.artifact_repo import ArtifactRepository
from spider.capability.registry import CapabilityRegistry
from spider.policy.engine import PolicyEngine
from spider.providers.manager import ProviderManager
from spider.ingest.queue import IngestQueue
from spider.resolution.resolver import EntityResolutionEngine
from spider.resolution.rebuilder import KnowledgeGraphRebuilder
from spider.explain.explainer import ExplainEngine
from spider.graph.projections import AnalyticalGraphProjector
from spider.core.engine import SpiderEngine
from spider.models.case import Case
from spider.models.target import Target
from spider.models.enums import ObservableType, ProviderState
from spider.models.budget import ExecutionBudget

class SpiderService:
    """
    Unified Service API Boundary for SPIDER.
    Exposes clean async methods for CLI, future UI, and optional MCP tools.
    Zero direct coupling to external tool binaries or CLI flags.
    """
    def __init__(
        self,
        db_path: str = "data/spider.db",
        artifacts_dir: str = "data/runs",
        capabilities_path: str = "config/capabilities.yaml",
        policies_path: str = "config/policies.yaml"
    ):
        self.db_manager = DatabaseManager(db_path=db_path)
        self.db_writer = SingleDBWriter(self.db_manager)
        self.is_running: bool = False
        self.artifact_repo = ArtifactRepository(artifacts_dir=artifacts_dir)
        self.ingest_queue = IngestQueue(self.db_writer)
        self.provider_manager = ProviderManager(self.artifact_repo, self.ingest_queue, self.db_writer)
        self.capability_registry = CapabilityRegistry(config_path=capabilities_path)
        self.policy_engine = PolicyEngine(config_path=policies_path)
        self.resolution_engine = EntityResolutionEngine()
        self.rebuilder = KnowledgeGraphRebuilder(self.resolution_engine)
        self.engine = SpiderEngine(
            db_manager=self.db_manager,
            db_writer=self.db_writer,
            provider_manager=self.provider_manager,
            capability_registry=self.capability_registry,
            policy_engine=self.policy_engine,
            resolution_engine=self.resolution_engine
        )
        self._started = False
        self._stopping = False
        self.background_tasks: set[asyncio.Task] = set()
        from spider.service.actions import InvestigationActions
        self.actions = InvestigationActions(self)

    async def start(self) -> None:
        if self._started:
            return
        await self.db_manager.initialize()
        if self.provider_manager.http_plane.closed:
            from spider.providers.http_plane import HTTPPlane
            from spider.providers.limits import OriginLimits
            old_plane = self.provider_manager.http_plane
            self.provider_manager.http_plane = HTTPPlane(factory=old_plane.factory, clock=old_plane.clock)
            # A restarted service may be attached to a new event loop.
            self.provider_manager.origin_limits = OriginLimits()
            self.provider_manager._global_slots = asyncio.Semaphore(4)
            self.provider_manager._provider_slots = {
                pid: asyncio.Semaphore(1) for pid in self.provider_manager.adapters
            }
        await self.db_writer.start()
        # A prior process cannot still own these full-engine tasks. Runs with a
        # durable frontier become explicitly cancelled and resumable; action
        # receipts without a checkpoint retain UNKNOWN_AFTER_RESTART semantics.
        async def recover_checkpointed_runs(session):
            from sqlalchemy import select, func
            from spider.storage.schema import ProviderRunRecord, TaskRunRecord, ObservationRecord
            from spider.models.base import utc_now
            rows = list((await session.scalars(select(ProviderRunRecord).where(
                ProviderRunRecord.status.in_(("QUEUED", "RUNNING"))))).all())
            for row in rows:
                metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
                checkpoint = metadata.get("checkpoint") or {}
                if checkpoint.get("version") != 1 or not checkpoint.get("frontier"):
                    continue
                row.status, row.completed_at = "CANCELLED", utc_now()
                tasks = list((await session.scalars(select(TaskRunRecord).where(
                    TaskRunRecord.run_id == row.id))).all())
                for task in tasks:
                    if task.status in ("PENDING", "QUEUED", "RUNNING"):
                        task.status, task.completed_at = "CANCELLED", utc_now()
                row.tasks_count = len(tasks)
                row.observations_count = await session.scalar(select(func.count()).select_from(
                    ObservationRecord).where(ObservationRecord.run_id == row.id,
                                             ObservationRecord.provider_id != "seed_target"))
        await self.db_writer.submit(recover_checkpointed_runs)
        self.is_running = True
        self._started = True
        self._stopping = False

    async def stop(self) -> None:
        if not self._started:
            return
        self._stopping = True
        async with self.actions._admission:
            tasks = list(self.background_tasks)
        for task in tasks:
            if not task.cancelling():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            # A task cancelled before its first instruction cannot run its own cleanup.
            from sqlalchemy import update
            from spider.storage.schema import ProviderRunRecord
            from spider.models.base import utc_now
            run_ids = [task.get_name().removeprefix("spider-run:") for task in tasks
                       if task.get_name().startswith("spider-run:")]
            async def cancel_unfinished(session):
                await session.execute(update(ProviderRunRecord).where(
                    ProviderRunRecord.id.in_(run_ids),
                    ProviderRunRecord.status.in_(["QUEUED", "RUNNING"]),
                ).values(status="CANCELLED", completed_at=utc_now()))
            await self.db_writer.submit(cancel_unfinished)
        await self.provider_manager.http_plane.aclose()
        await self.db_writer.stop()
        self.is_running = False
        await self.db_manager.close()
        self._started = False

    async def create_case(self, name: str, description: Optional[str] = None, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        case = Case(name=name, description=description, tags=tags or [])
        async def _create(session):
            rec = await CaseRepository.create_case(session, case)
            return {"id": rec.id, "name": rec.name, "status": rec.status, "created_at": rec.created_at.isoformat()}
        return await self.db_writer.submit(_create)

    async def list_cases(self) -> List[Dict[str, Any]]:
        async with self.db_manager.session_factory() as session:
            records = await CaseRepository.list_cases(session)
            return [{"id": r.id, "name": r.name, "status": r.status, "created_at": r.created_at.isoformat()} for r in records]

    async def add_target(self, case_id: str, raw_input: str, observable_type: ObservableType, scope_authorized: bool = False, *, canonical_value: str = "", namespace: str = "", metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        target = Target(
            case_id=case_id,
            observable_type=observable_type,
            namespace=namespace,
            raw_input=raw_input,
            scope_authorized=scope_authorized,
            canonical_value=canonical_value,
            metadata=metadata or {}
        )
        async def _add(session):
            rec = await CaseRepository.add_target(session, target)
            return {"id": rec.id, "case_id": rec.case_id, "canonical_value": rec.canonical_value, "type": rec.observable_type}
        return await self.db_writer.submit(_add)

    async def investigate(self, case_id: str, budget: Optional[ExecutionBudget] = None,
                          policy_profile: Optional[str] = None, run_id: Optional[str] = None,
                          investigation_mode=None, browser_assisted: bool = False,
                          resume_from_run_id: Optional[str] = None) -> Dict[str, Any]:
        from uuid import uuid4
        run_id = run_id or str(uuid4())
        try:
            return await self.engine.run_investigation(
                case_id, budget=budget, policy_profile=policy_profile, run_id=run_id,
                investigation_mode=investigation_mode, browser_assisted=browser_assisted,
                resume_from_run_id=resume_from_run_id)
        except asyncio.CancelledError:
            from sqlalchemy import select, func
            from spider.storage.schema import ProviderRunRecord, TaskRunRecord, ObservationRecord
            from spider.models.base import utc_now
            async def cancel(session):
                row = await session.get(ProviderRunRecord, run_id)
                if row and row.status in ("QUEUED", "RUNNING"):
                    row.status, row.completed_at = "CANCELLED", utc_now()
                    row.tasks_count = await session.scalar(select(func.count()).select_from(
                        TaskRunRecord).where(TaskRunRecord.run_id == run_id))
                    row.observations_count = await session.scalar(select(func.count()).select_from(
                        ObservationRecord).where(ObservationRecord.run_id == run_id,
                                                 ObservationRecord.provider_id != "seed_target"))
            await self.db_writer.submit(cancel)
            raise

    async def get_case_entities(self, case_id: str) -> List[Dict[str, Any]]:
        async with self.db_manager.session_factory() as session:
            records = await GraphRepository.get_entities_for_case(session, case_id)
            return [{
                "id": r.id,
                "canonical_name": r.canonical_name,
                "type": r.observable_type,
                "namespace": r.namespace,
                "observation_count": r.observation_count,
                "first_seen": r.first_seen.isoformat(),
                "last_seen": r.last_seen.isoformat()
            } for r in records]

    async def get_case_assertions(self, case_id: str) -> List[Dict[str, Any]]:
        async with self.db_manager.session_factory() as session:
            records = await GraphRepository.get_assertions_for_case(session, case_id)
            return [{
                "id": r.id,
                "source_entity_id": r.source_entity_id,
                "target_entity_id": r.target_entity_id,
                "assertion_type": r.assertion_type,
                "confidence": r.confidence,
                "independent_source_count": r.independent_source_count,
                "source_families": r.source_families
            } for r in records]

    async def explain_assertion(self, assertion_id: str) -> Optional[Dict[str, Any]]:
        async with self.db_manager.session_factory() as session:
            return await ExplainEngine.explain_assertion(session, assertion_id)

    async def get_graph_summary(self, case_id: str) -> Dict[str, Any]:
        async with self.db_manager.session_factory() as session:
            g = await AnalyticalGraphProjector.build_networkx_graph(session, case_id)
            return AnalyticalGraphProjector.compute_summary_metrics(g)

    async def rebuild_case(self, case_id: str) -> Dict[str, Any]:
        async def _rebuild(session):
            return await self.rebuilder.rebuild_case(session, case_id)
        return await self.db_writer.submit(_rebuild)

    async def check_provider_health(self) -> Dict[str, Any]:
        health_map = await self.provider_manager.check_all_health()
        return {pid: {"state": h.state.value, "message": h.message, "details": h.details,
            "contract_verified": h.contract_verified, "live_verified": h.live_verified,
            "provider_version": h.provider_version, "latency_ms": h.latency_ms} for pid, h in health_map.items()}

    async def doctor(self) -> Dict[str, Any]:
        health = await self.check_provider_health()
        return {
            "status": "HEALTHY",
            "database_connected": True,
            "wal_mode_enabled": True,
            "providers": health,
            "registered_capabilities": list(self.capability_registry.capabilities.keys()),
            "policy_profiles": list(self.policy_engine.profiles.keys())
        }
