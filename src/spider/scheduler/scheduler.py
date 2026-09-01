from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel
from spider.models.enums import ObservableType, NetworkClass
from spider.models.observable import NormalizedObservable
from spider.models.execution import ExecutionKey
from spider.models.budget import ExecutionBudget, BudgetLedger
from spider.models.policy import PolicyContext
from spider.capability.registry import CapabilityRegistry
from spider.scheduler.heuristics import calculate_task_priority

class ScheduledTask(BaseModel):
    execution_key: ExecutionKey
    priority_score: float
    capability: str
    provider_id: str
    target_observable: NormalizedObservable
    depth: int

class DeterministicScheduler:
    def __init__(self, capability_registry: CapabilityRegistry, budget: Optional[ExecutionBudget] = None):
        self.registry = capability_registry
        self.budget = budget or ExecutionBudget()
        self.ledger = BudgetLedger()

    def schedule_candidate_tasks(
        self,
        observable: NormalizedObservable,
        entity_id: str,
        policy_context: PolicyContext,
        provider_network_classes: Dict[str, NetworkClass],
        executed_keys: Set[str],
        available_providers: Optional[Set[str]] = None,
        depth: int = 0,
        is_seed: bool = False
    ) -> List[ScheduledTask]:
        """
        Evaluates capabilities for an observable, filters by available providers, policy & budget, and produces deterministic prioritized tasks.
        """
        if self.ledger.is_exhausted(self.budget, current_depth=depth):
            return []

        candidates: List[ScheduledTask] = []
        matching_caps = self.registry.get_capabilities_for_input(observable.type)

        for cap in matching_caps:
            for provider_id in cap.default_providers:
                # Check if provider adapter is registered & available
                if available_providers is not None and provider_id not in available_providers:
                    continue

                # Check policy
                prov_net_class = provider_network_classes.get(provider_id, NetworkClass.THIRD_PARTY_ONLY)
                if not policy_context.is_action_allowed(prov_net_class):
                    continue

                exec_key = ExecutionKey(
                    entity_id=entity_id,
                    capability=cap.name,
                    provider_id=provider_id,
                    configuration_hash="default"
                )

                if exec_key.key_string in executed_keys:
                    continue

                priority = calculate_task_priority(cap.name, provider_id, depth, is_seed)
                candidates.append(
                    ScheduledTask(
                        execution_key=exec_key,
                        priority_score=priority,
                        capability=cap.name,
                        provider_id=provider_id,
                        target_observable=observable,
                        depth=depth
                    )
                )

        # Deterministic sorting
        candidates.sort(key=lambda t: (-t.priority_score, t.capability, t.provider_id))
        return candidates
