"""Repeatable synthetic read benchmark; never uses real settings or providers."""
import asyncio
import json
import math
import platform
import tempfile
import time
from pathlib import Path
from spider.mcp.server import SpiderMCPServer
from spider.models.enums import ObservableType as T
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage
from spider.service.service import SpiderService
from spider.storage.repositories.observation_repo import ObservationRepository


async def benchmark(count=200, repeats=20):
    with tempfile.TemporaryDirectory(prefix="spider-digest-") as temp:
        service = SpiderService(str(Path(temp)/"case.db"), str(Path(temp)/"runs"))
        await service.start()
        try:
            case = await service.create_case("Synthetic benchmark")
            target = await service.add_target(case["id"], "fixture", T.USERNAME)
            observations = [Observation(observable=NormalizedObservable(
                type=T.ACCOUNT, value=f"fixture{i}@synthetic"), lineage=SourceLineage(
                case_id=case["id"], seed_id=target["id"], run_id="synthetic", task_id="synthetic",
                provider_id="fixture", provider_version="1", parent_observable_value="fixture",
                parent_observable_type=T.USERNAME)) for i in range(count)]
            async def ingest(session):
                await ObservationRepository.append_observations_batch(session, observations)
                await service.resolution_engine.resolve_observations(session, observations, case["id"])
            await service.db_writer.submit(ingest)
            server = SpiderMCPServer(service)
            results = {}
            for tool in ("query_case", "case_digest"):
                times, sizes = [], []
                for _ in range(repeats):
                    start = time.perf_counter()
                    response = await server.handle_tool_call(tool, {
                        "case_id": case["id"], "target_id": target["id"], "limit": 20})
                    times.append((time.perf_counter()-start)*1000)
                    sizes.append(len(json.dumps(response).encode()))
                times.sort()
                results[tool] = {"p50_ms": round(times[math.ceil(repeats*.5)-1], 3),
                                 "p95_ms": round(times[math.ceil(repeats*.95)-1], 3),
                                 "response_bytes": max(sizes)}
            return {"label": "EXPERIMENT RESULT", "dataset": "synthetic-200-accounts-v1",
                    "samples_per_path": repeats, "network_requests": 0,
                    "python": platform.python_version(), "architecture": platform.machine(),
                    "measurement": "single process; alternating paths not randomized; first iteration included",
                    "comparison": "legacy full graph vs new first page; different response scopes",
                    "results": results, "token_counts_measured": False,
                    "db_queue": service.db_writer.metrics}
        finally:
            await service.stop()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(benchmark()), indent=2))
