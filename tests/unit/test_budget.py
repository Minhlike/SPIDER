import pytest
from spider.models.budget import ExecutionBudget, BudgetLedger

def test_budget_exhaustion_conditions():
    budget = ExecutionBudget(
        max_entities=10,
        max_requests=20,
        max_depth=2,
        max_provider_calls=5,
        diminishing_returns_cutoff=3
    )
    ledger = BudgetLedger()

    # Initial state
    assert ledger.is_exhausted(budget, current_depth=0) is False

    # Depth cutoff
    assert ledger.is_exhausted(budget, current_depth=3) is True

    # Entities cutoff
    ledger.entities_count = 10
    assert ledger.is_exhausted(budget, current_depth=0) is True
    ledger.entities_count = 0

    # Provider calls cutoff
    ledger.provider_calls_count = 5
    assert ledger.is_exhausted(budget, current_depth=0) is True
    ledger.provider_calls_count = 0

    # Diminishing returns cutoff (3 consecutive zero yields)
    ledger.record_observation_yield(0)
    assert ledger.consecutive_zero_yield_runs == 1
    ledger.record_observation_yield(0)
    assert ledger.consecutive_zero_yield_runs == 2
    assert ledger.is_exhausted(budget, current_depth=0) is False
    ledger.record_observation_yield(0)
    assert ledger.consecutive_zero_yield_runs == 3
    assert ledger.is_exhausted(budget, current_depth=0) is True

    # Recovery resets counter
    ledger.record_observation_yield(5)
    assert ledger.consecutive_zero_yield_runs == 0
    assert ledger.is_exhausted(budget, current_depth=0) is False
