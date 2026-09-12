from pydantic import Field, PrivateAttr
from threading import Lock
import secrets
from typing import Literal, Optional
from spider.models.base import SpiderBaseModel

class ExecutionBudget(SpiderBaseModel):
    max_entities: int = Field(default=500, ge=0)
    max_depth: int = 3
    # None means the user deliberately selected no SPIDER-imposed total cap.
    # Per-provider timeouts, provider quotas/rate limits and policy checks still
    # apply, so an unlimited investigation cannot turn into an unbounded call.
    max_requests: Optional[int] = Field(default=100, ge=0)
    max_runtime_seconds: Optional[int] = Field(default=300, ge=1)
    per_action_timeout_seconds: int = Field(default=180, ge=1, le=900)
    username_site_limit: Literal[0, 50, 500] = 500
    username_source_scope: Literal["VN_COMMON_CORE", "GLOBAL_50", "GLOBAL_500", "GLOBAL_ALL"] = "VN_COMMON_CORE"
    # Conservative default after shared-cap/cancellation/deterministic-ingest gates.
    max_parallel_tasks: int = Field(default=2, ge=1, le=4)
    max_provider_calls: Optional[int] = Field(default=50, ge=0)
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
    request_events_dropped_count: int = 0
    _entities: set = PrivateAttr(default_factory=set)
    _task_request_counts: dict = PrivateAttr(default_factory=dict)
    _task_cache_counts: dict = PrivateAttr(default_factory=dict)
    _lock: Lock = PrivateAttr(default_factory=Lock)
    _fingerprint_salt: bytes = PrivateAttr(default_factory=lambda: secrets.token_bytes(32))

    def request(self, budget: ExecutionBudget, provider_id: str, protocol: str = "HTTP", kind: str = "request", *, task_id: str | None = None):
        """Count a dispatch attempt before transport I/O; failed attempts also cost one."""
        with self._lock:
            if budget.max_requests is not None and self.requests_count >= budget.max_requests:
                raise RequestBudgetExceeded()
            self.requests_count += 1
            event = {"sequence": self.requests_count, "provider_id": provider_id,
                     "protocol": protocol, "kind": kind}
            if task_id is not None:
                event["task_id"] = task_id
                self._task_request_counts[task_id] = self._task_request_counts.get(task_id, 0) + 1
            if len(self.request_events) < 1000:
                self.request_events.append(event)
            else:
                self.request_events_dropped_count += 1

    @property
    def attributed_requests_count(self):
        return self.requests_count

    def for_task(self, task_id: str):
        return TaskBudgetLedger(self, task_id)

    def count_for_task(self, task_id: str):
        with self._lock:
            return self._task_request_counts.get(task_id, 0)

    def admit_entity(self, budget: ExecutionBudget, case_id: str, observable) -> bool:
        admitted, _ = self.admit_entity_with_novelty(budget, case_id, observable)
        return admitted

    def admit_entity_with_novelty(self, budget: ExecutionBudget, case_id: str, observable):
        """Atomically admit an identity and report whether it was new to this run."""
        key = (case_id, *observable.identity)
        with self._lock:
            if key in self._entities:
                return True, False
            if self.entities_count >= budget.max_entities:
                self.entities_rejected_count += 1
                return False, False
            self._entities.add(key)
            self.entities_count += 1
            return True, True

    def record_observation_yield(self, count: int) -> None:
        if count == 0:
            self.consecutive_zero_yield_runs += 1
        else:
            self.consecutive_zero_yield_runs = 0

    def record_cache_hit(self, *, task_id=None):
        with self._lock:
            self.cache_hits_count += 1
            if task_id is not None:
                self._task_cache_counts[task_id] = self._task_cache_counts.get(task_id, 0) + 1

    def cache_count_for_task(self, task_id):
        with self._lock:
            return self._task_cache_counts.get(task_id, 0)

    def admitted_entity_keys(self):
        with self._lock:
            return set(self._entities)

    def restore_admitted_entity_keys(self, identities):
        with self._lock:
            self._entities = {tuple(identity) for identity in identities}

    def is_exhausted(self, budget: ExecutionBudget, current_depth: int = 0) -> bool:
        if self.entities_count >= budget.max_entities:
            return True
        if budget.max_requests is not None and self.requests_count >= budget.max_requests:
            return True
        if budget.max_provider_calls is not None and self.provider_calls_count >= budget.max_provider_calls:
            return True
        if current_depth > budget.max_depth:
            return True
        # Minimum source coverage for a seed must not be cut short merely
        # because earlier independent providers returned no rows.  Diminishing
        # returns only controls derived/pivot branches after depth zero.
        if current_depth > 0 and self.consecutive_zero_yield_runs >= budget.diminishing_returns_cutoff:
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

    def record_cache_hit(self):
        self._shared.record_cache_hit(task_id=self._task_id)

    @property
    def attributed_cache_hits_count(self):
        return self._shared.cache_count_for_task(self._task_id)
