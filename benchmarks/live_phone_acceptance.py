"""Run one consented, visible Cốc Cốc PHONE acceptance without printing identity data."""
import argparse
import asyncio
from collections import Counter
import json
import sys

from spider.models.budget import BudgetLedger, ExecutionBudget
from spider.models.classifier import TargetClassifier
from spider.models.enums import ObservableType
from spider.models.observable import NormalizedObservable
from spider.models.provenance import SourceLineage
from spider.providers.browser.coccoc import CocCocBrowserAdapter


async def run(phone):
    classified = TargetClassifier.resolve(phone, ObservableType.PHONE)
    target = NormalizedObservable(type=classified.detected_type,
                                  value=classified.canonical_value)
    adapter = CocCocBrowserAdapter()
    budget = ExecutionBudget(max_requests=500, max_runtime_seconds=90,
                             per_action_timeout_seconds=90)
    ledger = BudgetLedger()
    lineage = SourceLineage(
        case_id="live-acceptance", run_id="live-acceptance", task_id="phone-browser",
        provider_id=adapter.provider_id(), provider_version=adapter.version(),
        adapter_version=adapter.adapter_version(),
        parent_observable_value=target.canonical_value,
        parent_observable_type=ObservableType.PHONE,
        configuration_hash="live-phone-acceptance")
    result = await adapter.execute(
        target, lineage, request_ledger=ledger, execution_budget=budget,
        timeout_seconds=90, browser_parallel_tabs=3, phone_revalidate_limit=12)
    coverage = result.metadata.get("coverage", {})
    search = coverage.get("search_discovery", {})
    reasons = Counter(item.get("reason", "UNKNOWN")
                      for item in coverage.get("priority_sites", {}).values())
    classes = Counter(observation.raw_data.get("evidence_class", "NONE")
                      for observation in result.observations)
    return {"outcome": result.outcome, "duration_ms": round(result.duration_ms, 1),
            "requests": ledger.requests_count,
            "observations": len(result.observations),
            "checked_sources": coverage.get("checked"),
            "verified_mentions": search.get("verified_phone_mentions", 0),
            "unverified_leads": search.get("unverified_leads", 0),
            "evidence_classes": dict(classes),
            "source_reason_counts": dict(reasons),
            "revalidation_reason_counts": search.get("revalidation_reasons", {}),
            "source_outcomes": {source: {key: item.get(key) for key in (
                "outcome", "reason", "revalidation_reason") if item.get(key)}
                for source, item in coverage.get("priority_sites", {}).items()},
            "budget_reason": result.metadata.get("budget_reason")}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", required=True,
                        help="Consented phone target; never included in output")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.phone)), ensure_ascii=False))


if __name__ == "__main__":
    main()
