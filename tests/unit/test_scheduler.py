import pytest
from spider.capability.registry import CapabilityRegistry
from spider.capability.definitions import CapabilityDefinition
from spider.scheduler.scheduler import DeterministicScheduler
from spider.policy.engine import PolicyEngine
from spider.models.enums import ObservableType, NetworkClass
from spider.models.observable import NormalizedObservable
from spider.models.budget import ExecutionBudget
from spider.providers.fake.provider_a import FakeProviderA
from spider.providers.native.gravatar import GravatarPublicProfileAdapter
from spider.providers.native.public_profiles import PublicProfilesAdapter
from spider.providers.browser.coccoc import CocCocBrowserAdapter

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


def test_scheduler_fails_closed_when_yaml_and_adapter_contract_disagree():
    registry = CapabilityRegistry(config_path=None)
    registry.register_capability(CapabilityDefinition(
        name="WRONG_CAPABILITY", description="Deliberate contract mismatch",
        default_providers=["fake_a"],
        input_types=[ObservableType.EMAIL], output_types=[]))
    scheduler = DeterministicScheduler(registry)
    candidates = scheduler.schedule_candidate_tasks(
        observable=NormalizedObservable(type=ObservableType.EMAIL, value="owner@example.invalid"),
        entity_id="entity", policy_context=PolicyEngine().get_context("passive_standard"),
        provider_network_classes={"fake_a": NetworkClass.THIRD_PARTY_ONLY},
        executed_keys=set(), available_providers={"fake_a"},
        provider_adapters={"fake_a": FakeProviderA()}, depth=0, is_seed=True)
    assert candidates == []


def test_exact_email_profile_lookup_precedes_broader_public_search():
    registry = CapabilityRegistry(config_path="config/capabilities.yaml")
    scheduler = DeterministicScheduler(registry)
    adapters = {adapter.provider_id(): adapter for adapter in (
        GravatarPublicProfileAdapter(), PublicProfilesAdapter())}
    candidates = scheduler.schedule_candidate_tasks(
        observable=NormalizedObservable(type=ObservableType.EMAIL,
            value="owner@example.invalid"),
        entity_id="entity", policy_context=PolicyEngine().get_context("passive_standard"),
        provider_network_classes={provider_id: NetworkClass.THIRD_PARTY_ONLY
                                  for provider_id in adapters},
        executed_keys=set(), available_providers=set(adapters),
        provider_adapters=adapters, depth=0, is_seed=True)
    assert [candidate.provider_id for candidate in candidates] == [
        "gravatar_public", "github_public"]


def test_explicit_browser_discovery_precedes_broad_username_enumeration():
    registry = CapabilityRegistry(config_path="config/capabilities.yaml")
    scheduler = DeterministicScheduler(registry)
    from spider.providers.maigret.adapter import MaigretAdapter
    adapters = {adapter.provider_id(): adapter for adapter in (
        CocCocBrowserAdapter(), MaigretAdapter(), PublicProfilesAdapter())}
    candidates = scheduler.schedule_candidate_tasks(
        observable=NormalizedObservable(type=ObservableType.USERNAME, value="fixture-user"),
        entity_id="entity", policy_context=PolicyEngine().get_context("passive_standard"),
        provider_network_classes={provider_id: NetworkClass.THIRD_PARTY_ONLY
                                  for provider_id in adapters},
        executed_keys=set(), available_providers=set(adapters), provider_adapters=adapters,
        depth=0, is_seed=True,
        allowed_capabilities={"PUBLIC_PROFILE_LOOKUP", "USERNAME_DISCOVERY",
                              "BROWSER_PERSONAL_DISCOVERY"})
    assert candidates[0].provider_id == "coccoc_browser"
