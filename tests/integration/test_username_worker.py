import asyncio
import json

import pytest

from benchmarks.public_sites import public_sites
from spider.models.enums import ObservableType
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage
from spider.providers.maigret.adapter import MaigretAdapter


def target_and_lineage():
    return (NormalizedObservable(type=ObservableType.USERNAME, value="fixture-user"),
            SourceLineage(case_id="c", run_id="r", task_id="t", provider_id="maigret",
                          provider_version="0.6.5", parent_observable_value="fixture-user"))


@pytest.mark.asyncio
async def test_real_worker_reads_results_and_reports_coverage(tmp_path):
    with public_sites(tmp_path) as sites:
        result = await MaigretAdapter(database_path=sites["maigret"]).execute(*target_and_lineage(), timeout_seconds=20)
    assert len(result.observations) == 2, result.model_dump_json()
    assert result.observations[0].observable.canonical_value == "fixture-user@present"
    assert result.observations[0].raw_data["display_name"] == "Fixture Public Name"
    assert result.observations[0].raw_data["bio"] == "Public fixture biography"
    assert result.metadata["coverage"]["selected"] == 7
    assert result.metadata["coverage"]["checked"] == 7
    assert result.metadata["coverage"]["not_found"] == 2
    assert result.metadata["coverage"]["unknown"] == 4
    assert result.metadata["coverage"]["non_unique_detections"] == 1
    assert not any("wildcard" in o.observable.canonical_value for o in result.observations)
    assert result.outcome == "PARTIAL"


@pytest.mark.asyncio
async def test_time_budget_keeps_completed_sites(tmp_path):
    with public_sites(tmp_path, ["Present", "Slow"]) as sites:
        result = await MaigretAdapter(database_path=sites["maigret"]).execute(*target_and_lineage(), timeout_seconds=2.5)
    assert result.exit_code == 124
    assert len(result.observations) == 2
    assert result.metadata["coverage"]["unprocessed"] == 1


@pytest.mark.asyncio
async def test_cancel_reaps_exact_worker(tmp_path, monkeypatch):
    processes = []
    real_spawn = asyncio.create_subprocess_exec
    async def capture(*args, **kwargs):
        proc = await real_spawn(*args, **kwargs)
        processes.append(proc)
        return proc
    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)
    with public_sites(tmp_path, ["Slow"]) as sites:
        task = asyncio.create_task(MaigretAdapter(database_path=sites["maigret"]).execute(*target_and_lineage()))
        await asyncio.sleep(1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    assert processes and all(p.returncode is not None for p in processes)
