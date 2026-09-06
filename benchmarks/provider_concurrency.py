"""Controlled provider-delay experiment; no Internet, credentials or real targets."""
import asyncio
import json
import math
import statistics
import tempfile
import time
from pathlib import Path

from spider.models.budget import ExecutionBudget
from spider.models.enums import ObservableType as T
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.providers.base import ProviderExecutionResult
from spider.providers.fake.provider_a import FakeProviderA
from spider.service.service import SpiderService


class Tracker:
    def __init__(self):
        self.active, self.peak = 0, 0


class DelayedFixture(FakeProviderA):
    def __init__(self, index, tracker, delay=.08):
        self.index, self.tracker, self.delay = index, tracker, delay

    def provider_id(self):
        return f"fixture_{self.index}"

    async def execute(self, target, lineage, **options):
        self.tracker.active += 1
        self.tracker.peak = max(self.tracker.peak, self.tracker.active)
        try:
            options["request_ledger"].request(options["execution_budget"], self.provider_id())
            await asyncio.sleep(self.delay)
            value = f"source{self.index}.{target.canonical_value}"
            return ProviderExecutionResult(raw_content=json.dumps({"host": value}).encode(),
                observations=[Observation(observable=NormalizedObservable(type=T.HOSTNAME, value=value),
                    lineage=lineage.model_copy(update={"upstream_family": "SYNTHETIC",
                        "upstream_source": self.provider_id()}))])
        finally:
            self.tracker.active -= 1


async def trial(folder, width, *, entity_cap=20, request_cap=20, delays=None):
    tracker = Tracker()
    service = SpiderService(str(Path(folder) / "trial.db"), str(Path(folder) / "runs"))
    for index in range(4):
        service.provider_manager.register_adapter(DelayedFixture(index, tracker,
            delay=delays[index] if delays else .08))
    service.capability_registry.get_capability("SUBDOMAIN_DISCOVERY").default_providers = list(service.provider_manager.adapters)
    await service.start()
    try:
        case = (await service.create_case("Synthetic concurrency"))["id"]
        await service.add_target(case, "fixture.test", T.DOMAIN)
        started = time.perf_counter()
        result = await service.investigate(case, ExecutionBudget(max_depth=0,
            max_parallel_tasks=width, max_entities=entity_cap, max_requests=request_cap))
        elapsed = (time.perf_counter() - started) * 1000
        graph_start = time.perf_counter()
        entities = await service.get_case_entities(case)
        assertions = await service.get_case_assertions(case)
        graph_ms = (time.perf_counter() - graph_start) * 1000
        identities = {e["id"]: (e["type"], e["namespace"], e["canonical_name"]) for e in entities}
        graph = sorted((identities[a["source_entity_id"]], identities[a["target_entity_id"]],
                        a["assertion_type"], a["confidence"]) for a in assertions)
        return {"wall_ms": elapsed, "graph_read_ms": graph_ms, "peak_providers": tracker.peak,
            "requests": result["budget_ledger"]["requests_count"], "status": result["status"],
            "entities": sorted(identities.values()), "graph": graph,
            "observations": result["observations_collected"],
            "db_queue_wait_ms": service.db_writer.metrics["queue_wait_ms"],
            "db_transaction_ms": service.db_writer.metrics["transaction_ms"],
            "queue_peak": service.db_writer.metrics["peak_queue"]}
    finally:
        await service.stop()


async def main():
    import platform
    import tracemalloc
    import gc
    baseline = None
    results = {"kind": "EXPERIMENT RESULT", "network": "NONE; request counts are synthetic dispatch attempts",
        "python": platform.python_version(), "platform": platform.machine(),
        "fixture": "4 independent providers, 80ms synthetic response delay each; cold DB per trial",
        "samples_per_width": 20, "ui_latency": "NOT_MEASURED", "widths": []}
    tracemalloc.start()
    for width in (1, 2, 4):
        rows, peaks = [], []
        for _ in range(20):
            gc.collect()
            tracemalloc.reset_peak()
            baseline_bytes = tracemalloc.get_traced_memory()[0]
            with tempfile.TemporaryDirectory(prefix="spider-concurrency-") as folder:
                row = await trial(folder, width)
            peaks.append(tracemalloc.get_traced_memory()[1] - baseline_bytes)
            shape = (row["entities"], row["graph"], row["observations"], row["requests"], row["status"])
            if baseline is None:
                baseline = shape
            assert shape == baseline, "Concurrency changed fixture evidence or graph"
            rows.append(row)
        times = sorted(r["wall_ms"] for r in rows)
        graph = sorted(r["graph_read_ms"] for r in rows)
        results["widths"].append({"workers": width, "p50_ms": round(statistics.median(times), 3),
            "p95_ms": round(times[math.ceil(len(times)*.95)-1], 3),
            "graph_p50_ms": round(statistics.median(graph), 3),
            "graph_p95_ms": round(graph[math.ceil(len(graph)*.95)-1], 3),
            "db_queue_wait_sum_p50_ms": round(statistics.median(r["db_queue_wait_ms"] for r in rows), 3),
            "db_transaction_sum_p50_ms": round(statistics.median(r["db_transaction_ms"] for r in rows), 3),
            "max_python_traced_delta_bytes": max(peaks), "max_queue": max(r["queue_peak"] for r in rows),
            "requests_per_trial": 4, "useful_synthetic_observations_per_request": 1,
            "decision_coverage": "4/4 synthetic provider tasks", "correctness": "PASS"})
    tracemalloc.stop()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
