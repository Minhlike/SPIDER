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
    assert ledger.is_exhausted(budget, current_depth=1) is True
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
    # A seed still needs minimum source coverage.  Diminishing returns only
    # stop pivot/derived work after the root source set has been considered.
    assert ledger.is_exhausted(budget, current_depth=0) is False
    assert ledger.is_exhausted(budget, current_depth=1) is True

    # Recovery resets counter
    ledger.record_observation_yield(5)
    assert ledger.consecutive_zero_yield_runs == 0
    assert ledger.is_exhausted(budget, current_depth=0) is False


def test_unlimited_request_and_provider_call_budgets_still_count_usage():
    budget = ExecutionBudget(max_requests=None, max_provider_calls=None,
                             max_runtime_seconds=None, max_entities=10)
    ledger = BudgetLedger()

    for _ in range(25):
        ledger.request(budget, "fixture")
        ledger.provider_calls_count += 1

    assert ledger.requests_count == 25
    assert ledger.provider_calls_count == 25
    assert ledger.is_exhausted(budget) is False
    assert budget.model_dump(mode="json")["max_requests"] is None
    assert budget.model_dump(mode="json")["max_runtime_seconds"] is None
