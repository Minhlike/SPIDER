from pydantic import Field, PrivateAttr
from threading import Lock
import secrets
from typing import Literal
from spider.models.base import SpiderBaseModel

class ExecutionBudget(SpiderBaseModel):
    max_entities: int = Field(default=500, ge=0)
    max_depth: int = 3
    max_requests: int = Field(default=100, ge=0)
    max_runtime_seconds: int = 300
    username_site_limit: Literal[0, 50, 500] = 500
    username_source_scope: Literal["VN_COMMON_CORE", "GLOBAL_50", "GLOBAL_500", "GLOBAL_ALL"] = "VN_COMMON_CORE"
    max_parallel_tasks: int = 4
    max_provider_calls: int = 50
    max_branch_work: int = 20
    diminishing_returns_cutoff: int = 3

class BudgetLedger(SpiderBaseModel):
    entities_count: int = 0
    requests_count: int = 0
    provider_calls_count: int = 0
    consecutive_zero_yield_runs: int = 0
    cache_hits_count: int = 0
    entities_rejected_count: int = 0
    request_events: list[dict] = Field(default_factory=list)
    _entities: set = PrivateAttr(default_factory=set)
    _task_request_counts: dict = PrivateAttr(default_factory=dict)
    _lock: Lock = PrivateAttr(default_factory=Lock)
    _fingerprint_salt: bytes = PrivateAttr(default_factory=lambda: secrets.token_bytes(32))

    def request(self, budget: ExecutionBudget, provider_id: str, protocol: str = "HTTP", kind: str = "request", *, task_id: str | None = None):
        """Count a dispatch attempt before transport I/O; failed attempts also cost one."""
        with self._lock:
            if self.requests_count >= budget.max_requests:
                raise RequestBudgetExceeded()
            self.requests_count += 1
            event = {"sequence": self.requests_count, "provider_id": provider_id,
                     "protocol": protocol, "kind": kind}
            if task_id is not None:
                event["task_id"] = task_id
                self._task_request_counts[task_id] = self._task_request_counts.get(task_id, 0) + 1
            self.request_events.append(event)

    @property
    def attributed_requests_count(self):
        return self.requests_count

    def for_task(self, task_id: str):
        return TaskBudgetLedger(self, task_id)

    def count_for_task(self, task_id: str):
        with self._lock:
            return self._task_request_counts.get(task_id, 0)

    def admit_entity(self, budget: ExecutionBudget, case_id: str, observable) -> bool:
        key = (case_id, *observable.identity)
        with self._lock:
            if key in self._entities:
                return True
            if self.entities_count >= budget.max_entities:
                self.entities_rejected_count += 1
                return False
            self._entities.add(key)
            self.entities_count += 1
            return True

    def record_observation_yield(self, count: int) -> None:
        if count == 0:
            self.consecutive_zero_yield_runs += 1
        else:
            self.consecutive_zero_yield_runs = 0

    def record_cache_hit(self):
        with self._lock:
            self.cache_hits_count += 1

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


class RequestBudgetExceeded(Exception):
    def __init__(self):
        super().__init__("Network request budget exhausted")


class TaskBudgetLedger:
    """Shared hard cap, explicit task receipts; no ambient async/thread context."""
    def __init__(self, shared: BudgetLedger, task_id: str):
        self._shared, self._task_id = shared, task_id

    def __getattr__(self, name):
        return getattr(self._shared, name)

    @property
    def attributed_requests_count(self):
        return self._shared.count_for_task(self._task_id)

    def request(self, budget, provider_id, protocol="HTTP", kind="request"):
        self._shared.request(budget, provider_id, protocol, kind, task_id=self._task_id)
