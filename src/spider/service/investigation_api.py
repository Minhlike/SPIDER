"""Agent/UI investigation reads; evidence scope is enforced before graph access."""
import hashlib
import json
import math
from types import SimpleNamespace
from sqlalchemy import select
from spider.models.enums import ObservableType
from spider.capability.applicability import assess_provider
from spider.capability.scopes import PERSONAL_CAPABILITIES
from spider.service.projection import project
from spider.service.coverage import coverage_report
from spider.service.read_snapshot import make_cursor, make_snapshot, read_cursor, read_snapshot
from spider.service.evidence_analysis import public_url
from spider.service.phone_candidates import public_phone_candidates
from spider.service.questions import assess_questions, DEFAULT_QUESTIONS
from spider.storage.schema import TaskRunRecord, ProviderRunRecord, CaseRecord, TargetRecord
from spider.explain.explainer import ExplainEngine


async def list_context(session, case_id=None, limit=20, after=None):
    """ID-ordered navigation without loading graph, metadata or raw evidence."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid limit")
    model = TargetRecord if case_id is not None else CaseRecord
    query = select(model)
    if case_id is not None:
        if await session.get(CaseRecord, case_id) is None:
            raise ValueError("Unknown case")
        query = query.where(TargetRecord.case_id == case_id)
    if after is not None:
        cursor = await session.get(model, after)
        if cursor is None or (case_id is not None and cursor.case_id != case_id):
            raise ValueError("Invalid cursor")
        query = query.where(model.id > after)
    rows = list((await session.scalars(query.order_by(model.id).limit(limit + 1))).all())
    items = [{"id": r.id, "type": r.observable_type, "namespace": r.namespace[:128],
              "value": r.canonical_value[:512]} if case_id is not None else
             {"id": r.id, "name": r.name[:255], "status": r.status} for r in rows[:limit]]
    return {"items": items, "more": len(rows) > limit,
            "next_cursor": items[-1]["id"] if len(rows) > limit else None}


async def explain_claim(session, case_id, target_id, claim_id):
    view = await project(session, case_id, target_id)
    if claim_id not in {assertion.id for assertion in view.assertions}:
        raise ValueError("Claim outside target scope")
    explanation = await ExplainEngine.explain_assertion(session, claim_id)
    if explanation is None:
        raise ValueError("Claim not found")
    explanation["case_id"] = case_id
    explanation["target_id"] = view.seed.id
    return explanation


def input_catalogue(service):
    result = []
    for kind in ObservableType:
        providers = sorted({pid
            for cap in service.capability_registry.get_capabilities_for_input(kind)
            for pid in cap.default_providers
            if assess_provider(service.provider_manager.get_adapter(pid), kind, cap.name).applicable
            and service.provider_manager.get_adapter(pid).request_budget_supported})
        result.append({"type": kind.value, "providers": providers,
                       "supported": bool(providers), "live_verified": False,
                       "reason": "CAPABILITY_AVAILABLE" if providers else "NO_METERED_CAPABILITY"})
    return result


def _stamp(value):
    return value.isoformat() if value is not None else ""


async def plan_preview(session, service, case_id, target_id, question="all", snapshot=None):
    """Build a stable, read-only candidate plan from one scoped snapshot."""
    view = await project(session, case_id, target_id, question)
    if view.seed is None:
        raise ValueError("Target required")
    evidence = sorted(view.evidence_observations, key=lambda row: (_stamp(row.created_at), row.id))
    tasks = list((await session.scalars(select(TaskRunRecord).where(
        TaskRunRecord.case_id == case_id).order_by(TaskRunRecord.started_at, TaskRunRecord.id))).all())
    tasks = [row for row in tasks if (row.metadata_json or {}).get("seed_id") == view.seed.id]
    if snapshot is None:
        snapshot = make_snapshot("plan_preview", case_id, view.seed.id, question, {
            "evidence": [_stamp(evidence[-1].created_at), evidence[-1].id] if evidence else None,
            "tasks": [_stamp(tasks[-1].started_at), tasks[-1].id] if tasks else None,
        })
    bounds = read_snapshot(snapshot, "plan_preview", case_id, view.seed.id, question)
    evidence_bound, task_bound = bounds.get("evidence"), bounds.get("tasks")
    evidence = [row for row in evidence if evidence_bound is not None and
                (_stamp(row.created_at), row.id) <= tuple(evidence_bound)]
    tasks = [row for row in tasks if task_bound is not None and
             (_stamp(row.started_at), row.id) <= tuple(task_bound)]

    root = (view.seed.observable_type, view.seed.namespace, view.seed.canonical_value)
    evidence_identities = {(row.observable_type, row.namespace, row.canonical_value) for row in evidence}
    bounded_entities = [entity for entity in view.finding_entities
                        if (entity.observable_type, entity.namespace, entity.canonical_name) in evidence_identities]
    question_state = assess_questions(SimpleNamespace(seed=view.seed,
        finding_entities=bounded_entities), tasks)
    if question != "all":
        personal = question == "public_profiles"
        question_state["questions"] = [row for row in question_state["questions"]
            if any((capability in PERSONAL_CAPABILITIES) == personal
                   for capability in row["next_capabilities"])]
        kept = {row["id"] for row in question_state["questions"]}
        question_state["unresolved_gaps"] = [gap for gap in question_state["unresolved_gaps"]
                                                if gap["question_id"] in kept]

    seed_kind = ObservableType(view.seed.observable_type)
    root_entity = next((entity for entity in view.entities if
        (entity.observable_type, entity.namespace, entity.canonical_name) == root), None)
    attempted = {(row.capability, row.provider_id): row.status for row in tasks}
    candidates, blocked = [], []
    for row in sorted(question_state["questions"], key=lambda item: item["id"]):
        if row["status"] == "ANSWERED":
            continue
        for capability_name in sorted(row["next_capabilities"]):
            capability = service.capability_registry.get_capability(capability_name)
            if capability is None or seed_kind not in capability.input_types:
                blocked.append({"question_id": row["id"], "capability": capability_name,
                                "provider": None, "reason": "CAPABILITY_NOT_AVAILABLE_FOR_TYPED_SEED"})
                continue
            for provider_id in sorted(capability.default_providers):
                adapter = service.provider_manager.get_adapter(provider_id)
                decision = assess_provider(adapter, seed_kind, capability_name)
                reason = decision.reason if not decision.applicable else (
                    "UNMETERED_PROVIDER" if not adapter.request_budget_supported else None)
                if (capability_name, provider_id) in attempted:
                    reason = "ALREADY_ATTEMPTED_IN_SNAPSHOT"
                if root_entity is None:
                    reason = "TYPED_SEED_ENTITY_NOT_MATERIALIZED"
                if reason:
                    blocked.append({"question_id": row["id"], "capability": capability_name,
                                    "provider": provider_id, "reason": reason,
                                    "task_status": attempted.get((capability_name, provider_id))})
                    continue
                candidate = {"question_id": row["id"], "question_version": row["version"],
                    "capability": capability_name, "provider": provider_id,
                    "entity_id": root_entity.id, "observable_type": seed_kind.value,
                    "namespace": view.seed.namespace, "direct_seed": True,
                    "required_evidence_ids": [], "dispatch": False,
                    "basis": "UNRESOLVED_QUESTION_AND_REGISTERED_TYPED_CAPABILITY",
                    "verification": {"provider_contract": "REGISTERED_ONLY",
                                     "provider_live": "NOT_CHECKED"},
                    "admission_checks": ["POLICY_CHECK", "REQUEST_AND_ENTITY_BUDGET"],
                    "unverified_before_dispatch": ["PROVIDER_HEALTH"],
                    "browser_intent_required": capability_name == "BROWSER_PERSONAL_DISCOVERY"}
                candidate["candidate_key"] = hashlib.sha256(json.dumps(candidate,
                    sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                candidates.append(candidate)
    candidates.sort(key=lambda item: (item["question_id"], item["capability"], item["provider"]))
    blocked.sort(key=lambda item: (item["question_id"], item["capability"], item.get("provider") or ""))
    plan_core = {"question_registry_version": DEFAULT_QUESTIONS.version,
                 "capability_registry_version": service.capability_registry.version,
                 "question_state": question_state, "candidates": candidates, "blocked": blocked}
    fingerprint = hashlib.sha256(json.dumps(plan_core, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    state = "READY" if candidates else ("SATISFIED" if not question_state["unresolved_gaps"] else "BLOCKED")
    return {"case_id": case_id, "target_id": view.seed.id, "question": question,
            "snapshot": snapshot, "plan_schema_version": "1", "plan_fingerprint": fingerprint,
            "state": state, "deterministic_from_snapshot": True,
            "automatic_dispatch": False, **plan_core}


async def graph_neighbors(session, service, case_id, target_id, entity_id, limit=20,
                          after=None, snapshot=None):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid limit")
    view = await project(session, case_id, target_id)
    entity = next((e for e in view.entities if e.id == entity_id), None)
    if entity is None:
        raise ValueError("Entity outside target scope")
    edges = sorted((a for a in view.assertions if entity_id in
                    (a.source_entity_id, a.target_entity_id)), key=lambda a: (_stamp(a.first_observed), a.id))
    if snapshot is None:
        snapshot = make_snapshot("graph_neighbors", case_id, view.seed.id, entity_id, {
            "edges": [_stamp(edges[-1].first_observed), edges[-1].id] if edges else None})
    bounds = read_snapshot(snapshot, "graph_neighbors", case_id, view.seed.id, entity_id)
    bound = bounds.get("edges")
    edges = [a for a in edges if bound is not None and (_stamp(a.first_observed), a.id) <= tuple(bound)]
    start = 0
    if after is not None:
        after_id = read_cursor(after, snapshot)
        positions = {a.id: i for i, a in enumerate(edges)}
        if after_id not in positions:
            raise ValueError("Cursor does not belong to selected graph")
        start = positions[after_id] + 1
    page = edges[start:start + limit]
    ids = {x for a in page for x in (a.source_entity_id, a.target_entity_id)}
    kind = ObservableType(entity.observable_type)
    root_identity = (view.seed.observable_type, view.seed.namespace, view.seed.canonical_value)
    direct = (entity.observable_type, entity.namespace, entity.canonical_name) == root_identity
    action_evidence_ids = sorted(o.id for o in view.evidence_observations
        if (o.observable_type, o.namespace, o.canonical_value) ==
           (entity.observable_type, entity.namespace, entity.canonical_name))
    transforms = []
    for cap in service.capability_registry.get_capabilities_for_input(kind):
        for pid in cap.default_providers:
            adapter = service.provider_manager.get_adapter(pid)
            if assess_provider(adapter, kind, cap.name).applicable and adapter.request_budget_supported:
                transforms.append({"capability": cap.name, "provider": pid,
                    "network_class": adapter.network_class().value, "dispatch": False,
                    "basis": "REGISTERED_CAPABILITY_FOR_TYPED_ENTITY",
                    "scope": {"case_id": case_id, "target_id": view.seed.id,
                              "entity_id": entity.id, "direct_seed": direct},
                    "required_evidence_ids": [] if direct else action_evidence_ids,
                    "target_scope_authorized": bool(view.seed.scope_authorized) if direct else False})
    return {"entity_id": entity_id, "target_id": view.seed.id,
            "entities": [{"id": e.id, "type": e.observable_type,
                          "value": e.canonical_name[:512], "namespace": e.namespace[:128]} for e in view.entities if e.id in ids],
            "snapshot": snapshot,
            "edges": [{"id": a.id, "source": a.source_entity_id, "target": a.target_entity_id,
                       "type": a.assertion_type} for a in page],
            "more": start + len(page) < len(edges),
            "next_cursor": make_cursor(snapshot, page[-1].id) if page and start + len(page) < len(edges) else None,
            "transforms": transforms,
            "evidence_ids": [o.id for o in view.evidence_observations
                if (o.observable_type, o.namespace, o.canonical_value) ==
                   (entity.observable_type, entity.namespace, entity.canonical_name)][:limit]}


async def compare_runs(session, case_id, target_id, before_id, after_id, limit=20,
                       after=None, snapshot=None):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid limit")
    view = await project(session, case_id, target_id)
    if view.seed is None:
        raise ValueError("Target required")
    for run_id in (before_id, after_id):
        run = await session.get(ProviderRunRecord, run_id)
        if (run is None or run.case_id != case_id or target_id not in
                (run.metadata_json or {}).get("expected_sources", {})):
            raise ValueError("Run outside selected target")
    if snapshot is None:
        evidence = sorted(view.evidence_observations, key=lambda o: (_stamp(o.created_at), o.id))
        snapshot = make_snapshot("compare_runs", case_id, view.seed.id, f"{before_id}:{after_id}", {
            "evidence": [_stamp(evidence[-1].created_at), evidence[-1].id] if evidence else None})
    bounds = read_snapshot(snapshot, "compare_runs", case_id, view.seed.id, f"{before_id}:{after_id}")
    bound = bounds.get("evidence")
    def identities(run_id):
        return {(o.observable_type, o.namespace, o.canonical_value)
                for o in view.evidence_observations if o.run_id == run_id and bound is not None
                and (_stamp(o.created_at), o.id) <= tuple(bound)}
    before, after_values = identities(before_id), identities(after_id)
    added, not_observed = sorted(after_values - before), sorted(before - after_values)
    changes = [("ADDED", value) for value in added] + [("NOT_OBSERVED_IN_AFTER_RUN", value) for value in not_observed]
    changes.sort(key=lambda item: (item[0], item[1]))
    start = 0
    if after is not None:
        marker = read_cursor(after, snapshot)
        positions = {hashlib.sha256(repr(change).encode()).hexdigest(): i for i, change in enumerate(changes)}
        if marker not in positions:
            raise ValueError("Cursor does not belong to selected comparison")
        start = positions[marker] + 1
    page = changes[start:start + limit]
    page_items = [{"change": kind, "type": value[0], "namespace": value[1][:128],
                   "value": value[2][:512]} for kind, value in page]
    next_cursor = (make_cursor(snapshot, hashlib.sha256(repr(page[-1]).encode()).hexdigest())
                   if page and start + len(page) < len(changes) else None)
    return {"before_run": before_id, "after_run": after_id,
            "added": added[:limit], "not_observed_in_after_run": not_observed[:limit],
            "counts": {"added": len(added), "not_observed": len(not_observed)},
            "snapshot": snapshot, "changes": page_items, "next_cursor": next_cursor,
            "more": start + len(page) < len(changes),
            "truncated": max(len(added), len(not_observed)) > limit,
            "absence_verified": False}


async def run_coverage(session, case_id, target_id, run_id):
    view = await project(session, case_id, target_id)
    run = await session.get(ProviderRunRecord, run_id)
    if run is None or run.case_id != case_id or view.seed is None:
        raise ValueError("Invalid run scope")
    expected = (run.metadata_json or {}).get("expected_sources", {})
    if target_id not in expected:
        raise ValueError("Run outside target scope")
    tasks = list((await session.scalars(select(TaskRunRecord).where(
        TaskRunRecord.case_id == case_id, TaskRunRecord.run_id == run_id))).all())
    tasks = [t for t in tasks if (t.metadata_json or {}).get("seed_id") == target_id]
    return coverage_report(tasks, [o for o in view.evidence_observations if o.run_id == run_id], expected[target_id])


async def browser_trace(session, case_id, target_id, run_id):
    """Read a bounded, sanitized trace of browser tabs owned by this run only."""
    view = await project(session, case_id, target_id)
    run = await session.get(ProviderRunRecord, run_id)
    if run is None or run.case_id != case_id or view.seed is None:
        raise ValueError("Invalid browser trace scope")
    expected = (run.metadata_json or {}).get("expected_sources", {})
    if target_id not in expected:
        raise ValueError("Run outside target scope")
    tasks = list((await session.scalars(select(TaskRunRecord).where(
        TaskRunRecord.case_id == case_id, TaskRunRecord.run_id == run_id,
        TaskRunRecord.provider_id == "coccoc_browser").order_by(TaskRunRecord.id))).all())
    tasks = [task for task in tasks if (task.metadata_json or {}).get("seed_id") == target_id]
    if not tasks:
        raise ValueError("Browser trace unavailable")
    steps = []
    for task in tasks:
        workflow = (task.metadata_json or {}).get("browser_workflow", {})
        for step in workflow.get("steps", [])[:100]:
            if not isinstance(step, dict):
                continue
            steps.append({"action_id": str(step.get("action_id", ""))[:128],
                          "parent_observation_id": step.get("parent_observation_id"),
                          "step": str(step.get("step", "UNKNOWN"))[:64],
                          "source": str(step.get("source", "unknown"))[:64],
                          "sanitized_url": public_url(step.get("sanitized_url")),
                          "observed_at": step.get("observed_at"),
                          "content_sha256": str(step.get("content_sha256", ""))[:64] or None,
                          "state": str(step.get("state", "UNKNOWN"))[:64],
                          "reason": str(step.get("reason", "NOT_YET_VERIFIED"))[:128]})
    return {"case_id": case_id, "target_id": view.seed.id, "run_id": run_id,
            "owned_tabs_max": 3, "owned_tabs_closed": all(
                bool((task.metadata_json or {}).get("browser_workflow", {}).get("owned_tabs_closed"))
                for task in tasks), "automatic_replay": False,
            "resume": "NEW_EXPLICIT_ACTION_REQUIRED" if run.status != "COMPLETED" else "NOT_REQUIRED",
            "steps": steps, "identity_verified": False,
            "reader_note": {"vi": "Đây là nhật ký bước trình duyệt do SPIDER sở hữu. Kết quả bị chặn hoặc chưa rõ vẫn là dữ liệu chưa kết luận.",
                            "en": "This is a trace of browser tabs owned by SPIDER. Blocked or unclear results remain inconclusive."}}


async def phone_candidate_digest(session, case_id, target_id):
    view = await project(session, case_id, target_id, "all")
    if view.seed is None or view.seed.observable_type != "PHONE":
        raise ValueError("PHONE target required")
    return {"case_id": case_id, "target_id": view.seed.id,
            **public_phone_candidates(view.evidence_observations, view.seed.canonical_value)}


async def telemetry(session, case_id, target_id):
    view = await project(session, case_id, target_id)
    if view.seed is None:
        raise ValueError("Target required")
    tasks = list((await session.scalars(select(TaskRunRecord).where(
        TaskRunRecord.case_id == case_id))).all())
    groups = {}
    for task in tasks:
        m = task.metadata_json or {}
        if m.get("seed_id") != target_id:
            continue
        key = (task.provider_id, m.get("provider_version"), m.get("adapter_version"))
        groups.setdefault(key, []).append(task)
    # A useful item is a newly observed typed identity in this scoped question
    # with a recorded source family.  Seed input and duplicate identities are
    # not useful evidence, and replay cache hits are not network requests.
    first_seen = set()
    useful_by_task = {}
    for observation in sorted(view.evidence_observations, key=lambda item: (_stamp(item.created_at), item.id)):
        key = (observation.observable_type, observation.namespace, observation.canonical_value)
        sourced = bool(observation.upstream_family and observation.upstream_family != "UNKNOWN")
        if sourced and key not in first_seen:
            useful_by_task[observation.task_id] = useful_by_task.get(observation.task_id, 0) + 1
        first_seen.add(key)
    output = []
    for key, rows in sorted(groups.items(), key=lambda item: str(item[0])):
        durations = sorted(float(t.metadata_json["duration_ms"]) for t in rows
                           if type(t.metadata_json.get("duration_ms")) in (int, float)
                           and math.isfinite(t.metadata_json["duration_ms"])
                           and t.metadata_json["duration_ms"] >= 0)
        counted = [t.metadata_json["request_count"] for t in rows
                   if type(t.metadata_json.get("request_count")) is int
                   and t.metadata_json["request_count"] >= 0]
        requests = sum(counted) if len(counted) == len(rows) else None
        useful = sum(useful_by_task.get(task.id, 0) for task in rows)
        output.append({"provider": key[0], "version": key[1], "adapter_version": key[2],
            "samples": len(rows), "latency_samples": len(durations),
            "p50_ms": durations[math.ceil(len(durations)*.5)-1] if durations else None,
            "p95_ms": durations[math.ceil(len(durations)*.95)-1] if durations else None,
            "requests": requests, "request_samples": len(counted), "noncompleted_rate": sum(t.status != "COMPLETED" for t in rows)/len(rows),
            "useful_evidence_count": useful,
            "useful_evidence_per_request": useful / requests if requests else None,
            "reliability": "NOT_YET_CALIBRATED"})
    return {"providers": output, "scheduler_uses_telemetry": False}
