import asyncio
import json

import pytest

from benchmarks.public_sites import public_sites
from spider.models.enums import ObservableType
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage
from spider.providers.maigret.adapter import MaigretAdapter
from spider.providers.maigret.worker import priority_site_manifest, select_prioritized_sites
from spider.discovery.vn_sources import DIRECT_MAIGRET_SITES, SEARCH_ONLY_SITES


def target_and_lineage():
    return (NormalizedObservable(type=ObservableType.USERNAME, value="fixture-user"),
            SourceLineage(case_id="c", run_id="r", task_id="t", provider_id="maigret",
                          provider_version="0.6.5", parent_observable_value="fixture-user"))


def test_priority_social_sites_stay_inside_small_site_budget():
    sites = {"RankedOne": object(), "RankedTwo": object(), "Instagram": object(),
             "RankedThree": object(), "TikTok": object(), "Threads": object()}
    selected = select_prioritized_sites(sites, 4)
    assert list(selected) == ["Instagram", "Threads", "TikTok", "RankedOne"]
    assert priority_site_manifest(sites, sites, selected) == {
        "Instagram": {"state": "SCHEDULED", "site_name": "Instagram"},
        "Threads": {"state": "SCHEDULED", "site_name": "Threads"},
        "TikTok": {"state": "SCHEDULED", "site_name": "TikTok"},
    }


def test_priority_manifest_explains_missing_or_ineligible_platform():
    catalog = {"Instagram": object(), "Threads": object()}
    eligible = {"Instagram": catalog["Instagram"]}
    assert priority_site_manifest(catalog, eligible, {}) == {
        "Instagram": {"state": "SKIPPED_SITE_BUDGET", "site_name": "Instagram"},
        "Threads": {"state": "INELIGIBLE", "site_name": "Threads"},
        "TikTok": {"state": "NOT_IN_CATALOG"},
    }


def test_vietnam_common_scope_is_exact_and_never_claims_search_only_sites():
    sites = {name: object() for name in (*DIRECT_MAIGRET_SITES, *SEARCH_ONLY_SITES, "LongTail")}
    selected = select_prioritized_sites(sites, len(DIRECT_MAIGRET_SITES), DIRECT_MAIGRET_SITES)
    assert tuple(selected) == DIRECT_MAIGRET_SITES
    assert not set(SEARCH_ONLY_SITES) & set(selected)


def test_vietnam_common_scope_is_eligible_in_bundled_maigret_catalog():
    import maigret
    from pathlib import Path
    database = maigret.MaigretDatabase().load_from_file(
        str(Path(maigret.__file__).parent / "resources/data.json")
    )
    catalog = database.ranked_sites_dict(disabled=False, id_type="username")
    eligible = {name: site for name, site in catalog.items()
                if not site.activation and not site.similar_search
                and site.protocol in ("", "http", "https")}
    selected = select_prioritized_sites(
        eligible, len(DIRECT_MAIGRET_SITES), DIRECT_MAIGRET_SITES
    )
    assert tuple(selected) == DIRECT_MAIGRET_SITES


@pytest.mark.asyncio
async def test_real_worker_reads_results_and_reports_coverage(tmp_path):
    with public_sites(tmp_path) as sites:
        result = await MaigretAdapter(database_path=sites["maigret"]).execute(*target_and_lineage(), timeout_seconds=20)
    assert len(result.observations) == 2, result.model_dump_json()
    assert result.observations[0].observable.canonical_value == "fixture-user@present"
    assert result.observations[0].raw_data["display_name"] == "Fixture Public Name"
    assert result.observations[0].raw_data["bio"] == "Public fixture biography"
    assert result.observations[0].raw_data["explicit_links"] == [{
        "url": "https://linked.fixture.test/owner", "basis": "rel_me"}]
    assert result.metadata["coverage"]["selected"] == 7
    assert result.metadata["coverage"]["checked"] == 7
    assert result.metadata["coverage"]["not_found"] == 2
    assert result.metadata["coverage"]["unknown"] == 4
    assert result.metadata["coverage"]["non_unique_detections"] == 1
    assert not any("wildcard" in o.observable.canonical_value for o in result.observations)
    assert result.outcome == "PARTIAL"


@pytest.mark.asyncio
async def test_priority_platform_generic_shell_is_unknown_not_false_negative(tmp_path):
    with public_sites(tmp_path, ["SoftAbsent"]) as sites:
        database = json.loads(sites["maigret"].read_text(encoding="utf-8"))
        threads = database["sites"].pop("SoftAbsent")
        threads.update(checkType="message", presenseStrs=['og:type" content="profile'],
                       absenceStrs=['<title>Threads � Log in</title>'])
        database["sites"]["Threads"] = threads
        sites["maigret"].write_text(json.dumps(database), encoding="utf-8")
        result = await MaigretAdapter(database_path=sites["maigret"]).execute(
            *target_and_lineage(), timeout_seconds=10)
    assert not result.observations
    threads_status = result.metadata["coverage"]["priority_sites"]["Threads"]
    assert threads_status["state"] == "SCHEDULED"
    assert threads_status["outcome"] == "UNKNOWN"
    assert threads_status["reason"] == "PARSER_DRIFT"
    assert result.metadata["coverage"]["not_found"] == 0


@pytest.mark.asyncio
async def test_time_budget_keeps_raw_sites_but_cannot_promote_pending_controls(tmp_path):
    with public_sites(tmp_path, ["Present", "Slow"]) as sites:
        result = await MaigretAdapter(database_path=sites["maigret"]).execute(*target_and_lineage(), timeout_seconds=2.5)
    assert result.exit_code == 124
    assert not result.observations
    assert any(row.get("sitename") == "Present" for row in MaigretAdapter.rows(result.raw_content))
    assert result.metadata["coverage"]["controls_pending"] == 1
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


@pytest.mark.asyncio
@pytest.mark.parametrize("cap", [0, 1, 8])
async def test_real_worker_request_ledger_matches_server_including_control(tmp_path, cap):
    from spider.models.budget import BudgetLedger, ExecutionBudget
    ledger, budget = BudgetLedger(), ExecutionBudget(max_requests=cap)
    with public_sites(tmp_path, ["Present", "Wildcard"]) as sites:
        result = await MaigretAdapter(database_path=sites["maigret"]).execute(*target_and_lineage(),
            timeout_seconds=15, request_ledger=ledger, execution_budget=budget)
        assert ledger.requests_count == len(sites["requests"]) <= cap
    assert result.metadata["requests"] == ledger.requests_count
    if cap == 8:
        assert ledger.requests_count == 4
        assert sum(e["kind"] == "negative_control" for e in ledger.request_events) == 2
    if cap < 2:
        assert result.outcome in ("FAILED", "PARTIAL")
