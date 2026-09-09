"""Decision coverage is separate from attempted coverage and accuracy."""
STATES = {"ATTEMPTED", "CONFIRMED", "NOT_FOUND", "RATE_LIMITED", "BLOCKED", "TIMEOUT",
          "UNSUPPORTED", "SKIPPED_BUDGET", "BROKEN_PROVIDER"}


def collection_state(task, observation_count):
    metadata = task.metadata_json or {}
    reason = metadata.get("budget_reason")
    # Historical providers may keep a list of per-query outcomes here.  A
    # presentation failure must never hide an otherwise valid case report.
    if isinstance(reason, str) and reason in {"ENTITY_LIMIT", "REQUEST_LIMIT"}:
        return "SKIPPED_BUDGET"
    if reason == "UNMETERED_PROVIDER":
        return "UNSUPPORTED"
    if reason == "QUARANTINED":
        return "BLOCKED"
    state = metadata.get("collection_state")
    if isinstance(state, str) and state in STATES:
        return state
    if task.status in {"FAILED", "CANCELLED"}:
        return "BROKEN_PROVIDER"
    if observation_count:
        return "CONFIRMED"
    if task.status == "COMPLETED" and metadata.get("specific_negative_verified") is True:
        return "NOT_FOUND"
    return "ATTEMPTED"


def coverage_report(tasks, observations, expected):
    counts = {}
    for obs in observations:
        counts[obs.task_id] = counts.get(obs.task_id, 0) + 1
    steps = [{"provider_id": t.provider_id, "task_id": t.id,
              "state": collection_state(t, counts.get(t.id, 0)),
              "reason": ((t.metadata_json or {}).get("budget_reason") or
                         (t.metadata_json or {}).get("collection_reason") or t.error_message),
              "provider_version": (t.metadata_json or {}).get("provider_version"),
              "parser_version": (t.metadata_json or {}).get("adapter_version")} for t in tasks]
    attempted = {s["provider_id"] for s in steps}
    steps += [{"provider_id": pid, "task_id": None, "state": "SKIPPED_BUDGET", "reason": "Not dispatched in this run"}
              for pid in sorted(set(expected) - attempted)]
    decided = sum(s["state"] in {"CONFIRMED", "NOT_FOUND"} for s in steps)
    return {"expected_sources": sorted(set(expected)), "steps": steps,
            "attempted": sum(s["state"] not in {"UNSUPPORTED", "SKIPPED_BUDGET", "BLOCKED"} for s in steps),
            "decided": decided, "unknown": len(steps) - decided,
            "decision_coverage": decided / len(steps) if steps else None,
            "next_action": "REVIEW_UNKNOWN_REASONS" if len(steps) > decided else "REVIEW_EVIDENCE"}
