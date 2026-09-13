"""Offline benchmark for independently dispatched investigation actions."""
import argparse
import asyncio
import hashlib
import json
import statistics
import time
from pathlib import Path
from uuid import uuid4

from spider.capability.definitions import CapabilityDefinition
from spider.mcp.server import SpiderMCPServer
from spider.models.enums import ObservableType as T
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage
from spider.providers.fake.provider_a import FakeProviderA
from spider.providers.fake.provider_b import FakeProviderB
from spider.service.service import SpiderService
from spider.storage.repositories.observation_repo import ObservationRepository


class Tracker:
    def __init__(self):
        self.active = 0
        self.peak = 0

    async def wait(self, delay):
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(delay)
        finally:
            self.active -= 1


class DelayedActionA(FakeProviderA):
    def __init__(self, tracker, delay):
        self.tracker, self.delay = tracker, delay

    def provider_id(self):
        return "action_fixture_a"

    def capabilities(self):
        return ["ACTION_FIXTURE_A"]

    async def execute(self, target, lineage, **options):
        options["request_ledger"].request(options["execution_budget"], self.provider_id())
        await self.tracker.wait(self.delay)
        return await super().execute(target, lineage, **options)


class DelayedActionB(FakeProviderB):
    def __init__(self, tracker, delay):
        self.tracker, self.delay = tracker, delay

    def provider_id(self):
        return "action_fixture_b"

    def capabilities(self):
        return ["ACTION_FIXTURE_B"]

    async def execute(self, target, lineage, **options):
        options["request_ledger"].request(options["execution_budget"], self.provider_id())
        await self.tracker.wait(self.delay)
        return await super().execute(target, lineage, **options)


async def trial(folder, width, delay=.1):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    tracker = Tracker()
    service = SpiderService(str(folder / "spider.db"), str(folder / "runs"))
    providers = [DelayedActionA(tracker, delay), DelayedActionB(tracker, delay)]
    for provider in providers:
        service.provider_manager.register_adapter(provider)
    service.capability_registry.register_capability(CapabilityDefinition(
        name="ACTION_FIXTURE_A", description="Offline action benchmark A",
        input_types=[T.DOMAIN], output_types=[T.HOSTNAME, T.IP_ADDRESS],
        default_providers=[providers[0].provider_id()]))
    service.capability_registry.register_capability(CapabilityDefinition(
        name="ACTION_FIXTURE_B", description="Offline action benchmark B",
        input_types=[T.DOMAIN], output_types=[T.ASN, T.CIDR, T.ORGANIZATION],
        default_providers=[providers[1].provider_id()]))
    service.actions._execution = asyncio.Semaphore(width)
    await service.start()
    try:
        case = (await service.create_case("De-identified action benchmark"))["id"]
        target = (await service.add_target(case, "fixture.test", T.DOMAIN))["id"]
        seed = Observation(observable=NormalizedObservable(type=T.DOMAIN, value="fixture.test"),
            lineage=SourceLineage(case_id=case, run_id="seed", task_id="seed",
                seed_id=target, provider_id="seed_target", provider_version="1"))
        async def materialize_seed(session):
            await ObservationRepository.append_observations_batch(session, [seed])
            await service.resolution_engine.resolve_observations(session, [seed], case)
        await service.db_writer.submit(materialize_seed)
        entity = next(item for item in await service.get_case_entities(case)
                      if item["type"] == "DOMAIN")
        server = SpiderMCPServer(service)
        requests = [{"case_id": case, "target_id": target, "entity_id": entity["id"],
            "action_id": str(uuid4()), "capability": provider.capabilities()[0],
            "provider_id": provider.provider_id()} for provider in providers]
        started = time.perf_counter()
        receipts = await asyncio.gather(*(server.handle_tool_call("run_capability", row)
                                          for row in requests))
        tasks = list(service.background_tasks)
        if tasks:
            await asyncio.gather(*tasks)
        elapsed_ms = (time.perf_counter() - started) * 1000
        final = [await server.handle_tool_call("action_status", {
            key: row[key] for key in ("case_id", "target_id", "action_id")})
            for row in requests]
        identities = sorted((row["type"], row["namespace"], row["canonical_name"])
                            for row in await service.get_case_entities(case))
        correctness_hash = hashlib.sha256(json.dumps(identities,
            separators=(",", ":")).encode()).hexdigest()
        return {"width": width, "elapsed_ms": elapsed_ms, "peak_actions": tracker.peak,
                "statuses": [row["status"] for row in final],
                "requests": sum(row["requests_count"] for row in final),
                "correctness_hash": correctness_hash,
                "admitted": len({row["run_id"] for row in receipts})}
    finally:
        await service.stop()


async def run(output, repetitions, delay):
    output = Path(output)
    rows = []
    for width in (1, 2):
        for repetition in range(repetitions):
            rows.append(await trial(output / f"w{width}-{repetition}", width, delay))
    summary = {"label": "EXPERIMENT RESULT", "fixture": "OFFLINE_SYNTHETIC",
        "repetitions": repetitions, "results": {}}
    for width in (1, 2):
        samples = [row for row in rows if row["width"] == width]
        summary["results"][str(width)] = {
            "median_elapsed_ms": statistics.median(row["elapsed_ms"] for row in samples),
            "peak_actions": max(row["peak_actions"] for row in samples),
            "requests": sorted({row["requests"] for row in samples}),
            "correctness_hashes": sorted({row["correctness_hash"] for row in samples}),
            "statuses": sorted({status for row in samples for status in row["statuses"]})}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="test-results/action-concurrency")
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--delay", type=float, default=.1)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 100 or not .01 <= args.delay <= 2:
        raise SystemExit("Invalid bounded benchmark arguments")
    asyncio.run(run(args.output, args.repetitions, args.delay))


if __name__ == "__main__":
    main()
