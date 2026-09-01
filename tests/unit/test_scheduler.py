import pytest
from spider.capability.registry import CapabilityRegistry
from spider.capability.definitions import CapabilityDefinition
from spider.scheduler.scheduler import DeterministicScheduler
from spider.policy.engine import PolicyEngine
from spider.models.enums import ObservableType, NetworkClass
from spider.models.observable import NormalizedObservable
from spider.models.budget import ExecutionBudget

def test_deterministic_scheduler_priority_and_deduplication():
    registry = CapabilityRegistry(config_path="config/capabilities.yaml")
    budget = ExecutionBudget(max_depth=2, max_entities=10)
    scheduler = DeterministicScheduler(registry, budget)
    
    obs = NormalizedObservable(type=ObservableType.DOMAIN, value="example.com")
    policy_engine = PolicyEngine(config_path="config/policies.yaml")
    ctx = policy_engine.get_context("passive_standard")
    
    provider_classes = {"subfinder": NetworkClass.THIRD_PARTY_ONLY, "spiderfoot": NetworkClass.THIRD_PARTY_ONLY}
    executed = set()

    # First schedule call
    candidates1 = scheduler.schedule_candidate_tasks(
        observable=obs,
        entity_id="ent-1",
        policy_context=ctx,
        provider_network_classes=provider_classes,
        executed_keys=executed,
        depth=0,
        is_seed=True
    )
    assert len(candidates1) > 0
    first_task = candidates1[0]

    # Mark as executed
    executed.add(first_task.execution_key.key_string)

    # Second schedule call should not return the executed task
    candidates2 = scheduler.schedule_candidate_tasks(
        observable=obs,
        entity_id="ent-1",
        policy_context=ctx,
        provider_network_classes=provider_classes,
        executed_keys=executed,
        depth=0,
        is_seed=True
    )
    assert not any(c.execution_key.key_string == first_task.execution_key.key_string for c in candidates2)
