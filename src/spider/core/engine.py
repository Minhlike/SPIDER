from spider.providers.base import ProviderExecutionResult
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Set, Optional, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from spider.models.enums import ObservableType, ExecutionStatus, NetworkClass
from spider.models.observable import NormalizedObservable, canonicalize_observable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage
from spider.models.execution import ProviderRun, TaskRun, ExecutionKey
from spider.models.budget import ExecutionBudget, BudgetLedger
from spider.models.policy import PolicyContext
from spider.capability.registry import CapabilityRegistry
from spider.policy.engine import PolicyEngine
from spider.scheduler.scheduler import DeterministicScheduler, ScheduledTask
from spider.providers.manager import ProviderManager
from spider.ingest.queue import IngestQueue
from spider.storage.writer import SingleDBWriter
from spider.storage.database import DatabaseManager
from spider.storage.repositories.case_repo import CaseRepository
from spider.storage.repositories.observation_repo import ObservationRepository
from spider.storage.repositories.graph_repo import GraphRepository
from spider.storage.repositories.execution_repo import ExecutionRepository
from spider.resolution.resolver import EntityResolutionEngine

logger = logging.getLogger(__name__)

class SpiderEngine:
    def __init__(
        self,
        db_manager: DatabaseManager,
        db_writer: SingleDBWriter,
        provider_manager: ProviderManager,
        capability_registry: CapabilityRegistry,
        policy_engine: PolicyEngine,
        resolution_engine: Optional[EntityResolutionEngine] = None
    ):
        self.db_manager = db_manager
        self.db_writer = db_writer
        self.provider_manager = provider_manager
        self.capability_registry = capability_registry
        self.policy_engine = policy_engine
        self.resolution_engine = resolution_engine or EntityResolutionEngine()

    async def run_investigation(
        self,
        case_id: str,
        budget: Optional[ExecutionBudget] = None,
        policy_profile: Optional[str] = None,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes a deterministic capability-driven investigation loop for the given case.
        """
        budget = budget or ExecutionBudget()
        scheduler = DeterministicScheduler(self.capability_registry, budget)
        run_id = run_id or str(uuid.uuid4())

        # 1. Fetch case & targets
        async with self.db_manager.session_factory() as session:
            case_rec = await CaseRepository.get_case(session, case_id)
            if not case_rec:
                raise ValueError(f"Case {case_id} does not exist")
            targets = await CaseRepository.get_targets(session, case_id)
            if not targets:
                raise ValueError(f"Case {case_id} has no targets registered")

        # 2. Record ProviderRun
        provider_run = ProviderRun(
            id=run_id,
            case_id=case_id,
            status=ExecutionStatus.RUNNING
        )
        async def _init_run(session):
            await ExecutionRepository.create_provider_run(session, provider_run)
        await self.db_writer.submit(_init_run)

        # 3. Initialize Work Frontier from targets
        executed_key_hashes: Set[str] = set()
        frontier: List[Tuple[NormalizedObservable, str, int]] = []

        # Upsert seed targets as entities AND append to observation log
        for tgt in targets:
            norm_obs = NormalizedObservable(
                type=ObservableType(tgt.observable_type),
                value=tgt.raw_input,
                canonical_value=tgt.canonical_value
            )
            seed_lineage = SourceLineage(
                case_id=case_id,
                run_id=run_id,
                task_id="seed_initialization",
                provider_id="seed_target",
                provider_version="1.0.0",
                upstream_source="user_input",
                upstream_family="USER_SEED",
                parent_observable_value=None
            )
            seed_obs = Observation(
                observable=norm_obs,
                lineage=seed_lineage,
                confidence=1.0
            )
            async def _init_seed(session):
                await ObservationRepository.append_observation(session, seed_obs)
                await session.flush()
                await self.resolution_engine.resolve_observations(session, [seed_obs], case_id)
            await self.db_writer.submit(_init_seed)
            frontier.append((norm_obs, "", 0))

        # 4. Investigation Event Loop
        total_tasks_run = 0
        total_observations = 0
        available_providers = set(self.provider_manager.adapters.keys())

        while frontier and not scheduler.ledger.is_exhausted(budget):
            current_obs, parent_val, depth = frontier.pop(0)

            # Get entity ID
            async with self.db_manager.session_factory() as session:
                ent_rec = await GraphRepository.get_entity_by_canonical(session, case_id, current_obs.canonical_value)
                entity_id = ent_rec.id if ent_rec else str(uuid.uuid4())

            # Scope check
            is_in_scope = any(t.canonical_value == current_obs.canonical_value and t.scope_authorized for t in targets)
            policy_context = self.policy_engine.get_context(policy_profile, is_target_in_scope=is_in_scope)
            provider_net_classes = self.provider_manager.get_provider_network_classes()

            # Schedule candidate tasks
            candidates = scheduler.schedule_candidate_tasks(
                observable=current_obs,
                entity_id=entity_id,
                policy_context=policy_context,
                provider_network_classes=provider_net_classes,
                executed_keys=executed_key_hashes,
                available_providers=available_providers,
                depth=depth,
                is_seed=(depth == 0)
            )

            for cand in candidates:
                if scheduler.ledger.is_exhausted(budget, current_depth=depth):
                    break

                task = TaskRun(
                    case_id=case_id,
                    run_id=run_id,
                    execution_key_hash=cand.execution_key.key_string,
                    provider_id=cand.provider_id,
                    capability=cand.capability,
                    target_observable_value=current_obs.canonical_value,
                    status=ExecutionStatus.RUNNING
                )

                lineage = SourceLineage(
                    case_id=case_id,
                    run_id=run_id,
                    task_id=task.id,
                    provider_id=cand.provider_id,
                    provider_version="1.0.0",
                    adapter_version="1.0.0",
                    parent_observable_value=current_obs.canonical_value,
                    configuration_hash=cand.execution_key.configuration_hash
                )

                # Execute task via ProviderManager with bounded safety timeout
                try:
                    exec_result = await asyncio.wait_for(
                        self.provider_manager.execute_task(task, current_obs, lineage),
                        timeout=30.0
                    )
                except asyncio.TimeoutError:
                    exec_result = ProviderExecutionResult(
                        raw_content=b"Task timeout",
                        observations=[],
                        exit_code=124,
                        error_message="Task execution exceeded 30s timeout",
                        mime_type="text/plain"
                    )
                executed_key_hashes.add(cand.execution_key.key_string)
                total_tasks_run += 1
                scheduler.ledger.provider_calls_count += 1
                scheduler.ledger.record_observation_yield(len(exec_result.observations))

                if exec_result.observations:
                    total_observations += len(exec_result.observations)
                    
                    # Resolve observations into knowledge graph
                    async def _resolve_batch(session):
                        await self.resolution_engine.resolve_observations(session, exec_result.observations, case_id)
                    await self.db_writer.submit(_resolve_batch)

                    # Add newly discovered observables to frontier if within depth budget
                    if depth + 1 <= budget.max_depth:
                        for obs in exec_result.observations:
                            if obs.observable.canonical_value != current_obs.canonical_value:
                                frontier.append((obs.observable, current_obs.canonical_value, depth + 1))

        # 5. Complete ProviderRun
        async def _finish_run(session):
            provider_run.status = ExecutionStatus.COMPLETED
            provider_run.completed_at = datetime.now(timezone.utc)
            provider_run.tasks_count = total_tasks_run
            provider_run.observations_count = total_observations
            await ExecutionRepository.update_provider_run(session, provider_run)
        await self.db_writer.submit(_finish_run)

        # 6. Fetch final graph metrics
        async with self.db_manager.session_factory() as session:
            entities = await GraphRepository.get_entities_for_case(session, case_id)
            assertions = await GraphRepository.get_assertions_for_case(session, case_id)

        return {
            "run_id": run_id,
            "status": "COMPLETED",
            "tasks_executed": total_tasks_run,
            "observations_collected": total_observations,
            "entities_count": len(entities),
            "assertions_count": len(assertions),
            "budget_exhausted": scheduler.ledger.is_exhausted(budget)
        }
