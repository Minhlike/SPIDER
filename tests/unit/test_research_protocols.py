import pytest
from benchmarks.research_protocols import (score_email_benchmark,
    score_scheduler_holdout, score_username_manual_benchmark)


def test_overlap_accuracy_is_separate_from_incremental_coverage():
    rows = [
        {"fixture_id":"1" * 64,"service":"same","cohort":"OVERLAP","truth":"EXISTS","engine":"socialscan","outcome":"CONFIRMED_EXISTS","requests":1},
        {"fixture_id":"1" * 64,"service":"same","cohort":"OVERLAP","truth":"EXISTS","engine":"holehe","outcome":"UNKNOWN","requests":1},
        {"fixture_id":"2" * 64,"service":"extra","cohort":"HOLEHE_ONLY","truth":"EXISTS","engine":"holehe","outcome":"CONFIRMED_EXISTS","requests":1}]
    result = score_email_benchmark(rows)
    assert result["cohorts"]["OVERLAP"]["socialscan"]["recall"] == 1
    assert result["cohorts"]["HOLEHE_ONLY"]["holehe"]["decision_coverage"] == 1
    assert result["adoption_gate"] == "NOT_YET_VERIFIED"


def test_unknown_never_counts_as_negative_decision():
    row = {"fixture_id":"1" * 64,"service":"same","cohort":"OVERLAP","truth":"NOT_EXISTS",
           "engine":"holehe","outcome":"UNKNOWN","requests":1}
    assert score_email_benchmark([row])["cohorts"]["OVERLAP"]["holehe"]["decision_coverage"] == 0
    with pytest.raises(ValueError):
        score_email_benchmark([{**row, "outcome":"NOT_FOUND_BY_TIMEOUT"}])


def _paired_username_rows(count=100, spider_outcome=None):
    rows = []
    for index in range(count):
        truth = "PRESENT" if index < count // 2 else "ABSENT"
        for method in ("MANUAL", "SPIDER"):
            rows.append({"fixture_id": f"{index:064x}", "service": "fixture",
                "truth": truth, "method": method,
                "outcome": spider_outcome if method == "SPIDER" and spider_outcome else truth,
                "elapsed_ms": 1000 if method == "MANUAL" else 100,
                "requests": 1})
    return rows


def test_username_benchmark_only_passes_paired_sufficient_sample_at_manual_quality():
    result = score_username_manual_benchmark(_paired_username_rows())
    assert result["adoption_gate"] == "PASS"
    assert result["methods"]["SPIDER"]["precision"] == 1
    assert score_username_manual_benchmark(_paired_username_rows(10))["adoption_gate"] == "NOT_YET_VERIFIED"


def test_username_unknowns_reduce_recall_and_fail_full_sample_gate():
    result = score_username_manual_benchmark(_paired_username_rows(spider_outcome="UNKNOWN"))
    assert result["adoption_gate"] == "FAIL"
    assert result["methods"]["SPIDER"]["decision_coverage"] == 0


def _scheduler_rows(count=50, adaptive_hash=None, adaptive_coverage=.8,
                    adaptive_false=0):
    rows = []
    for index in range(count):
        fixture = f"{index:064x}"
        for strategy in ("STATIC", "ADAPTIVE"):
            rows.append({"fixture_id": fixture, "strategy": strategy,
                "correctness_hash": (adaptive_hash if strategy == "ADAPTIVE" and adaptive_hash
                                     else "a" * 64),
                "decision_coverage": .8 if strategy == "STATIC" else adaptive_coverage,
                "useful_evidence": 4, "requests": 5 if strategy == "STATIC" else 4,
                "wall_ms": 100 if strategy == "STATIC" else 80,
                "false_attributions": 0 if strategy == "STATIC" else adaptive_false})
    return rows


def test_scheduler_holdout_passes_same_correctness_with_lower_time_and_cost():
    result = score_scheduler_holdout(_scheduler_rows())
    assert result["adoption_gate"] == "PASS"
    assert result["checks"]["same_correctness"]
    assert result["metrics"]["ADAPTIVE"]["requests"] < result["metrics"]["STATIC"]["requests"]


def test_scheduler_holdout_stays_closed_for_small_or_harmful_sample():
    assert score_scheduler_holdout(_scheduler_rows(10))["adoption_gate"] == "NOT_YET_VERIFIED"
    harmful = score_scheduler_holdout(_scheduler_rows(
        adaptive_hash="b" * 64, adaptive_coverage=.7, adaptive_false=1))
    assert harmful["adoption_gate"] == "FAIL"
    with pytest.raises(ValueError):
        score_scheduler_holdout(_scheduler_rows()[:-1])
