"""Agent/UI investigation reads; evidence scope is enforced before graph access."""
import math
from sqlalchemy import select
from spider.models.enums import ObservableType
from spider.capability.applicability import assess_provider
from spider.service.projection import project
from spider.service.coverage import coverage_report
from spider.storage.schema import TaskRunRecord, ProviderRunRecord, CaseRecord, TargetRecord


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


async def graph_neighbors(session, service, case_id, target_id, entity_id, limit=20):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid limit")
    view = await project(session, case_id, target_id)
    entity = next((e for e in view.entities if e.id == entity_id), None)
    if entity is None:
        raise ValueError("Entity outside target scope")
    edges = sorted((a for a in view.assertions if entity_id in
                    (a.source_entity_id, a.target_entity_id)), key=lambda a: a.id)
    page = edges[:limit]
    ids = {x for a in page for x in (a.source_entity_id, a.target_entity_id)}
    kind = ObservableType(entity.observable_type)
    transforms = []
    for cap in service.capability_registry.get_capabilities_for_input(kind):
        for pid in cap.default_providers:
            adapter = service.provider_manager.get_adapter(pid)
            if assess_provider(adapter, kind, cap.name).applicable and adapter.request_budget_supported:
                transforms.append({"capability": cap.name, "provider": pid,
                    "network_class": adapter.network_class().value, "dispatch": False})
    return {"entity_id": entity_id, "target_id": view.seed.id,
            "entities": [{"id": e.id, "type": e.observable_type,
                          "value": e.canonical_name[:512], "namespace": e.namespace[:128]} for e in view.entities if e.id in ids],
            "edges": [{"id": a.id, "source": a.source_entity_id, "target": a.target_entity_id,
                       "type": a.assertion_type} for a in page],
            "more": len(edges) > limit, "transforms": transforms,
            "evidence_ids": [o.id for o in view.evidence_observations
                if (o.observable_type, o.namespace, o.canonical_value) ==
                   (entity.observable_type, entity.namespace, entity.canonical_name)][:limit]}


async def compare_runs(session, case_id, target_id, before_id, after_id, limit=20):
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
    def identities(run_id):
        return {(o.observable_type, o.namespace, o.canonical_value)
                for o in view.evidence_observations if o.run_id == run_id}
    before, after = identities(before_id), identities(after_id)
    added, not_observed = sorted(after - before), sorted(before - after)
    return {"before_run": before_id, "after_run": after_id,
            "added": added[:limit], "not_observed_in_after_run": not_observed[:limit],
            "counts": {"added": len(added), "not_observed": len(not_observed)},
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
        output.append({"provider": key[0], "version": key[1], "adapter_version": key[2],
            "samples": len(rows), "latency_samples": len(durations),
            "p50_ms": durations[math.ceil(len(durations)*.5)-1] if durations else None,
            "p95_ms": durations[math.ceil(len(durations)*.95)-1] if durations else None,
            "requests": requests, "request_samples": len(counted), "noncompleted_rate": sum(t.status != "COMPLETED" for t in rows)/len(rows),
            "useful_evidence_per_request": None, "reliability": "NOT_YET_CALIBRATED"})
    return {"providers": output, "scheduler_uses_telemetry": False}
