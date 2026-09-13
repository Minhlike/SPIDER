import pytest

from benchmarks.action_concurrency import trial


@pytest.mark.asyncio
async def test_action_width_two_preserves_results_and_overlaps_independent_providers(tmp_path):
    serial = await trial(tmp_path / "serial", 1, .05)
    parallel = await trial(tmp_path / "parallel", 2, .05)

    assert serial["peak_actions"] == 1
    assert parallel["peak_actions"] == 2
    assert serial["statuses"] == parallel["statuses"] == ["COMPLETED", "COMPLETED"]
    assert serial["requests"] == parallel["requests"] == 2
    assert serial["admitted"] == parallel["admitted"] == 2
    assert serial["correctness_hash"] == parallel["correctness_hash"]
