"""Pre-registered, offline scoring for future consented experiments; never performs requests."""
from collections import Counter
import re
from statistics import median

OUTCOMES = {"CONFIRMED_EXISTS", "CONFIRMED_NOT_EXISTS", "RATE_LIMITED", "UNKNOWN", "ERROR"}
DEIDENTIFIED_ID = re.compile(r"[0-9a-f]{64}")


def _require_deidentified_id(value):
    if not isinstance(value, str) or DEIDENTIFIED_ID.fullmatch(value) is None:
        raise ValueError("fixture_id must be a 64-character lowercase hex digest")


def validate_email_benchmark(rows):
    required = {"fixture_id", "service", "cohort", "truth", "engine", "outcome", "requests"}
    for row in rows:
        if set(row) != required or row["cohort"] not in {"OVERLAP", "HOLEHE_ONLY"} or row["outcome"] not in OUTCOMES:
            raise ValueError("Invalid pre-registered benchmark row")
        _require_deidentified_id(row["fixture_id"])
        if row["truth"] not in {"EXISTS", "NOT_EXISTS", "UNKNOWN"} or not isinstance(row["requests"], int) or row["requests"] < 0:
            raise ValueError("Invalid benchmark truth or request count")


def score_email_benchmark(rows):
    validate_email_benchmark(rows)
    result = {}
    for cohort in ("OVERLAP", "HOLEHE_ONLY"):
        cohort_rows = [r for r in rows if r["cohort"] == cohort]
        by_engine = {}
        for engine in sorted({r["engine"] for r in cohort_rows}):
            items = [r for r in cohort_rows if r["engine"] == engine]
            tp = sum(r["truth"] == "EXISTS" and r["outcome"] == "CONFIRMED_EXISTS" for r in items)
            fp = sum(r["truth"] != "EXISTS" and r["outcome"] == "CONFIRMED_EXISTS" for r in items)
            fn = sum(r["truth"] == "EXISTS" and r["outcome"] != "CONFIRMED_EXISTS" for r in items)
            decided = sum(r["outcome"] in {"CONFIRMED_EXISTS", "CONFIRMED_NOT_EXISTS"} for r in items)
            by_engine[engine] = {"precision": tp/(tp+fp) if tp+fp else None,
                "recall": tp/(tp+fn) if tp+fn else None, "false_positive": fp,
                "decision_coverage": decided/len(items) if items else None,
                "requests": sum(r["requests"] for r in items),
                "outcomes": dict(Counter(r["outcome"] for r in items))}
        result[cohort] = by_engine
    return {"label": "EXPERIMENT RESULT", "cohorts": result,
            "adoption_gate": "NOT_YET_VERIFIED", "note": "HOLEHE_ONLY is incremental coverage, never overlap accuracy"}


USERNAME_OUTCOMES = {
    "PRESENT", "ABSENT", "UNKNOWN", "LOGIN_REQUIRED", "RATE_LIMITED",
    "BLOCKED", "NETWORK_ERROR", "PARSER_DRIFT",
}


def validate_username_manual_benchmark(rows):
    """Validate paired, de-identified manual/SPIDER observations."""
    required = {"fixture_id", "service", "truth", "method", "outcome",
                "elapsed_ms", "requests"}
    seen = set()
    for row in rows:
        if set(row) != required or row["method"] not in {"MANUAL", "SPIDER"}:
            raise ValueError("Invalid username benchmark row")
        if row["truth"] not in {"PRESENT", "ABSENT"} or row["outcome"] not in USERNAME_OUTCOMES:
            raise ValueError("Invalid username benchmark truth or outcome")
        _require_deidentified_id(row["fixture_id"])
        if not isinstance(row["elapsed_ms"], (int, float)) or row["elapsed_ms"] < 0:
            raise ValueError("Invalid benchmark duration")
        if not isinstance(row["requests"], int) or row["requests"] < 0:
            raise ValueError("Invalid benchmark request count")
        key = (row["fixture_id"], row["service"], row["method"])
        if key in seen:
            raise ValueError("Duplicate username benchmark row")
        seen.add(key)
    manual = {(r["fixture_id"], r["service"], r["truth"]) for r in rows if r["method"] == "MANUAL"}
    spider = {(r["fixture_id"], r["service"], r["truth"]) for r in rows if r["method"] == "SPIDER"}
    if manual != spider:
        raise ValueError("Manual and SPIDER cohorts must be paired exactly")


def score_username_manual_benchmark(rows, minimum_cases=100,
                                    minimum_positive=30, minimum_negative=30):
    """Score automation against a manual baseline without inflating unknowns."""
    validate_username_manual_benchmark(rows)
    metrics = {}
    for method in ("MANUAL", "SPIDER"):
        items = [r for r in rows if r["method"] == method]
        tp = sum(r["truth"] == "PRESENT" and r["outcome"] == "PRESENT" for r in items)
        fp = sum(r["truth"] == "ABSENT" and r["outcome"] == "PRESENT" for r in items)
        fn = sum(r["truth"] == "PRESENT" and r["outcome"] != "PRESENT" for r in items)
        decided = sum(r["outcome"] in {"PRESENT", "ABSENT"} for r in items)
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        metrics[method] = {
            "precision": precision,
            "recall": recall,
            "f1": (2 * precision * recall / (precision + recall)
                   if precision is not None and recall is not None and precision + recall else None),
            "false_positive": fp,
            "decision_coverage": decided / len(items) if items else None,
            "median_elapsed_ms": median([r["elapsed_ms"] for r in items]) if items else None,
            "requests": sum(r["requests"] for r in items),
            "outcomes": dict(Counter(r["outcome"] for r in items)),
        }
    cases = len(rows) // 2
    positives = sum(r["truth"] == "PRESENT" for r in rows if r["method"] == "MANUAL")
    negatives = cases - positives
    sample_ready = cases >= minimum_cases and positives >= minimum_positive and negatives >= minimum_negative
    manual, spider = metrics["MANUAL"], metrics["SPIDER"]
    comparable = all(value is not None for value in (
        manual["precision"], manual["recall"], spider["precision"], spider["recall"],
        manual["decision_coverage"], spider["decision_coverage"],
        manual["median_elapsed_ms"], spider["median_elapsed_ms"],
    ))
    passes = comparable and all((
        spider["precision"] >= manual["precision"],
        spider["recall"] >= manual["recall"],
        spider["decision_coverage"] >= manual["decision_coverage"],
        spider["median_elapsed_ms"] <= manual["median_elapsed_ms"],
        spider["false_positive"] <= manual["false_positive"],
    ))
    gate = "PASS" if sample_ready and passes else "FAIL" if sample_ready else "NOT_YET_VERIFIED"
    return {"label": "EXPERIMENT RESULT", "adoption_gate": gate,
            "sample": {"paired_cases": cases, "positive": positives, "negative": negatives,
                       "minimum_cases": minimum_cases, "minimum_positive": minimum_positive,
                       "minimum_negative": minimum_negative},
            "methods": metrics,
            "note": "Unknown and blocked outcomes reduce recall/coverage; they are never counted as absence."}


SCHEDULER_STRATEGIES = {"STATIC", "ADAPTIVE"}


def validate_scheduler_holdout(rows):
    required = {"fixture_id", "strategy", "correctness_hash", "decision_coverage",
                "useful_evidence", "requests", "wall_ms", "false_attributions"}
    if not rows:
        raise ValueError("Scheduler holdout cannot be empty")
    seen = set()
    for row in rows:
        if set(row) != required or row["strategy"] not in SCHEDULER_STRATEGIES:
            raise ValueError("Invalid scheduler holdout row")
        _require_deidentified_id(row["fixture_id"])
        if not isinstance(row["correctness_hash"], str) or len(row["correctness_hash"]) != 64:
            raise ValueError("Invalid correctness hash")
        if (not isinstance(row["decision_coverage"], (int, float))
                or isinstance(row["decision_coverage"], bool)
                or not 0 <= row["decision_coverage"] <= 1):
            raise ValueError("Invalid decision coverage")
        for field in ("useful_evidence", "requests", "false_attributions"):
            if not isinstance(row[field], int) or isinstance(row[field], bool) or row[field] < 0:
                raise ValueError(f"Invalid {field}")
        if (not isinstance(row["wall_ms"], (int, float)) or isinstance(row["wall_ms"], bool)
                or row["wall_ms"] < 0):
            raise ValueError("Invalid wall time")
        key = row["fixture_id"], row["strategy"]
        if key in seen:
            raise ValueError("Duplicate scheduler holdout row")
        seen.add(key)
    expected = {row["fixture_id"] for row in rows}
    for strategy in SCHEDULER_STRATEGIES:
        if {row["fixture_id"] for row in rows if row["strategy"] == strategy} != expected:
            raise ValueError("STATIC and ADAPTIVE holdouts must be paired exactly")


def score_scheduler_holdout(rows, minimum_cases=50):
    """Decide whether adaptive ordering may leave shadow mode."""
    validate_scheduler_holdout(rows)
    by_strategy = {strategy: [row for row in rows if row["strategy"] == strategy]
                   for strategy in sorted(SCHEDULER_STRATEGIES)}
    metrics = {}
    for strategy, items in by_strategy.items():
        metrics[strategy] = {
            "cases": len(items),
            "median_wall_ms": median(row["wall_ms"] for row in items) if items else None,
            "requests": sum(row["requests"] for row in items),
            "useful_evidence": sum(row["useful_evidence"] for row in items),
            "mean_decision_coverage": (sum(row["decision_coverage"] for row in items) / len(items)
                                       if items else None),
            "false_attributions": sum(row["false_attributions"] for row in items),
        }
    pairs = {}
    for row in rows:
        pairs.setdefault(row["fixture_id"], {})[row["strategy"]] = row
    same_correctness = all(pair["STATIC"]["correctness_hash"] ==
                           pair["ADAPTIVE"]["correctness_hash"] for pair in pairs.values())
    static, adaptive = metrics["STATIC"], metrics["ADAPTIVE"]
    no_more_false_attribution = adaptive["false_attributions"] <= static["false_attributions"]
    time_cost_noninferior = (adaptive["median_wall_ms"] <= static["median_wall_ms"]
                             and adaptive["requests"] <= static["requests"])
    time_or_cost_improved = (adaptive["median_wall_ms"] < static["median_wall_ms"]
                             or adaptive["requests"] < static["requests"])
    coverage_improved = (adaptive["mean_decision_coverage"] >
                         static["mean_decision_coverage"])
    same_correctness_path = (same_correctness and no_more_false_attribution
                             and time_cost_noninferior and time_or_cost_improved)
    coverage_path = coverage_improved and no_more_false_attribution
    sample_ready = len(pairs) >= minimum_cases
    gate = "PASS" if sample_ready and (same_correctness_path or coverage_path) else (
        "FAIL" if sample_ready else "NOT_YET_VERIFIED")
    return {"label": "EXPERIMENT RESULT", "adoption_gate": gate,
            "sample": {"paired_cases": len(pairs), "minimum_cases": minimum_cases},
            "metrics": metrics,
            "checks": {"same_correctness": same_correctness,
                       "no_more_false_attribution": no_more_false_attribution,
                       "time_cost_noninferior": time_cost_noninferior,
                       "time_or_cost_improved": time_or_cost_improved,
                       "coverage_improved": coverage_improved},
            "note": "PASS authorizes a separate reviewed rollout; it does not change the scheduler."}
