import pytest
from spider.policy.engine import PolicyEngine
from spider.models.enums import NetworkClass

def test_policy_defaults_and_scopes():
    engine = PolicyEngine(config_path="config/policies.yaml")
    
    # Passive standard (default)
    ctx_passive = engine.get_context("passive_standard", is_target_in_scope=False)
    assert ctx_passive.is_action_allowed(NetworkClass.LOCAL_ONLY) is True
    assert ctx_passive.is_action_allowed(NetworkClass.THIRD_PARTY_ONLY) is True
    assert ctx_passive.is_action_allowed(NetworkClass.TARGET_DIRECT) is False
    assert ctx_passive.is_action_allowed(NetworkClass.TARGET_ACTIVE) is False

    # Active profile with out-of-scope target
    ctx_active_no_scope = engine.get_context("active_authorized", is_target_in_scope=False)
    assert ctx_active_no_scope.is_action_allowed(NetworkClass.TARGET_DIRECT) is False
    assert ctx_active_no_scope.is_action_allowed(NetworkClass.TARGET_ACTIVE) is False

    # Active profile with authorized in-scope target
    ctx_active_in_scope = engine.get_context("active_authorized", is_target_in_scope=True)
    assert ctx_active_in_scope.is_action_allowed(NetworkClass.TARGET_DIRECT) is True
    assert ctx_active_in_scope.is_action_allowed(NetworkClass.TARGET_ACTIVE) is True
