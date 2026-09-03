from pydantic import Field
from typing import Literal
from spider.models.base import SpiderBaseModel

class ExecutionBudget(SpiderBaseModel):
    max_entities: int = 500
    max_depth: int = 3
    max_requests: int = 100
    max_runtime_seconds: int = 300
    username_site_limit: Literal[0, 50, 500] = 500
    max_parallel_tasks: int = 4
    max_provider_calls: int = 50
    max_branch_work: int = 20
    diminishing_returns_cutoff: int = 3

class BudgetLedger(SpiderBaseModel):
    entities_count: int = 0
    requests_count: int = 0
    provider_calls_count: int = 0
    consecutive_zero_yield_runs: int = 0

    def record_observation_yield(self, count: int) -> None:
        if count == 0:
            self.consecutive_zero_yield_runs += 1
        else:
            self.consecutive_zero_yield_runs = 0

    def is_exhausted(self, budget: ExecutionBudget, current_depth: int = 0) -> bool:
        if self.entities_count >= budget.max_entities:
            return True
        if self.requests_count >= budget.max_requests:
            return True
        if self.provider_calls_count >= budget.max_provider_calls:
            return True
        if current_depth > budget.max_depth:
            return True
        if self.consecutive_zero_yield_runs >= budget.diminishing_returns_cutoff:
            return True
        return False
