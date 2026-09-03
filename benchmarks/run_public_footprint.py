"""Run from repository root: python -m benchmarks.run_public_footprint."""
import asyncio
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.public_sites import public_sites
from spider.models.enums import ObservableType
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage
from spider.providers.maigret.adapter import MaigretAdapter


def score(states, truth):
    positives = {name for name, state in states.items() if state.casefold() == "claimed"}
    tp = sum(truth[name] is True for name in positives)
    fp = sum(truth[name] is False for name in positives)
    unresolved_claims = sum(truth[name] is None for name in positives)
    fn = sum(value is True and name not in positives for name, value in truth.items())
    unknown_correct = sum(value is None and states.get(name, "Unknown").casefold() in ("unknown", "waf")
                          for name, value in truth.items())
    return {"true_positive": tp, "false_positive": fp, "false_negative": fn,
            "precision_known_cases": tp/(tp+fp) if tp+fp else None,
            "recall_known_cases": tp/(tp+fn) if tp+fn else None,
            "f1_known_cases": 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
            "known_decision_coverage": sum(value is not None and states.get(name, "").casefold() in ("claimed", "available")
                                           for name, value in truth.items()) / sum(value is not None for value in truth.values()),
            "unsupported_positive_claims": unresolved_claims,
            "unknowns_correct": unknown_correct,
            "unknowns_misreported_absent": sum(value is None and states.get(name, "").casefold() == "available"
                                               for name, value in truth.items())}


async def main():
    output = Path("test-results/public-footprint-benchmark")
    output.mkdir(parents=True, exist_ok=True)
    sherlock_python = Path("runtime/benchmarks/sherlock/Scripts/python.exe").resolve()
    if not sherlock_python.exists(): raise RuntimeError("Install the isolated Sherlock benchmark runtime first")
    results = []
    with tempfile.TemporaryDirectory(prefix="spider-benchmark-") as folder:
        with public_sites(folder) as sites:
            for repetition in range(3):
                # Rotate order to reduce startup/cache advantage.
                engines = ["spider", "maigret", "sherlock"]
                engines = engines[repetition:] + engines[:repetition]
                for engine in engines:
                    before = len(sites["requests"])
                    started = time.perf_counter()
                    if engine == "spider":
                        adapter = MaigretAdapter(database_path=sites["maigret"])
                        target = NormalizedObservable(type=ObservableType.USERNAME, value="fixture-user")
                        lineage = SourceLineage(case_id="benchmark", run_id="synthetic", task_id="local",
                            provider_id="maigret", provider_version="0.6.5", parent_observable_value="fixture-user")
                        result = await adapter.execute(target, lineage, timeout_seconds=30, username_site_limit=50)
                        states = {r["sitename"]: adapter.state(r).title() for r in adapter.rows(result.raw_content) if r.get("sitename")}
                        detail = {"states": states, "version": adapter.adapter_version(),
                                  "coverage": result.metadata["coverage"], "status": result.outcome}
                    else:
                        report = Path(folder) / f"{engine}-result.json"
                        python = sys.executable if engine == "maigret" else str(sherlock_python)
                        cmd = [python, "-m", "benchmarks.engine_worker", engine, str(sites[engine]), str(report)]
                        completed = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, timeout=30,
                            env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"))
                        if completed.returncode:
                            raise RuntimeError(f"{engine} failed: {completed.stderr.decode(errors='replace')[-1500:]}")
                        detail = json.loads(report.read_text())
                    detail.update(engine=engine, repetition=repetition+1,
                        elapsed_seconds=round(time.perf_counter()-started, 3),
                        requests=len(sites["requests"])-before,
                        scores=score(detail["states"], sites["truth"]))
                    results.append(detail)
            summary = [{"engine": engine, "median_seconds": statistics.median(r["elapsed_seconds"] for r in results if r["engine"] == engine),
                        "scores": next(r["scores"] for r in results if r["engine"] == engine)} for engine in ["spider", "maigret", "sherlock"]]
            report = {"at": datetime.now(timezone.utc).isoformat(), "truth": sites["truth"],
                "fixture_sha256": hashlib.sha256(Path("benchmarks/public_sites.py").read_bytes()).hexdigest(),
                "scope": "Seven synthetic local sites; three repetitions; no real identity data; not Internet-wide superiority",
                "summary": summary, "runs": results}
            (output / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(summary, indent=2))


if __name__ == "__main__": asyncio.run(main())
