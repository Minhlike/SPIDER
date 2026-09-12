"""Compact, read-only evidence pages. No provider dispatch or raw payload export."""
from sqlalchemy import select

from spider.service.projection import project
from spider.service.read_snapshot import make_cursor, make_snapshot, read_cursor, read_snapshot
from spider.storage.schema import CaseRecord, TaskRunRecord
from spider.service.questions import assess_questions
from spider.service.evidence_analysis import analyze


def _stamp(value):
    return value.isoformat() if value is not None else ""


def _within_bound(row, timestamp_field, bound):
    if bound is None:
        return False
    return (_stamp(getattr(row, timestamp_field)) or "", row.id) <= tuple(bound)


async def case_digest(session, case_id, target_id=None, question="all", limit=20, after=None,
                      snapshot=None, history_after=None):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    if await session.get(CaseRecord, case_id) is None:
        raise ValueError("Case not found")
    view = await project(session, case_id, target_id, question)
    if view.seed is None:
        raise ValueError("Select a target for this case")
    observations = sorted(view.evidence_observations, key=lambda o: (_stamp(o.created_at), o.id))
    tasks = list((await session.scalars(select(TaskRunRecord).where(
        TaskRunRecord.case_id == case_id).order_by(
        TaskRunRecord.started_at.desc(), TaskRunRecord.id))).all())
    tasks = [t for t in tasks if (t.metadata_json or {}).get("seed_id") == view.seed.id]
    if snapshot is None:
        snapshot = make_snapshot("case_digest", case_id, view.seed.id, question, {
            "evidence": [_stamp(observations[-1].created_at), observations[-1].id] if observations else None,
            "history": [_stamp(max(tasks, key=lambda t: (_stamp(t.started_at), t.id)).started_at),
                        max(tasks, key=lambda t: (_stamp(t.started_at), t.id)).id] if tasks else None,
        })
    bounds = read_snapshot(snapshot, "case_digest", case_id, view.seed.id, question)
    observations = [o for o in observations if _within_bound(o, "created_at", bounds.get("evidence"))]
    start = 0
    if after is not None:
        after_id = read_cursor(after, snapshot)
        positions = {o.id: i for i, o in enumerate(observations)}
        if after_id not in positions:
            raise ValueError("Cursor does not belong to selected evidence")
        start = positions[after_id] + 1
    page = observations[start:start + limit]
    tasks = [t for t in tasks if _within_bound(t, "started_at", bounds.get("history"))]
    tasks.sort(key=lambda t: (_stamp(t.started_at), t.id), reverse=True)
    history_start = 0
    if history_after is not None:
        history_id = read_cursor(history_after, snapshot)
        positions = {t.id: i for i, t in enumerate(tasks)}
        if history_id not in positions:
            raise ValueError("Cursor does not belong to selected history")
        history_start = positions[history_id] + 1
    history_page = tasks[history_start:history_start + limit]
    unresolved = sum(t.status != "COMPLETED" for t in tasks)
    entity_ids = {(e.observable_type, e.namespace, e.canonical_name): e.id for e in view.entities}
    question_state = assess_questions(view, tasks)
    evidence_analysis = analyze(observations)
    return {
        "explanation": {"vi": "Đây là trang bằng chứng của mục tiêu đã chọn. Bằng chứng còn thiếu hoặc nguồn chưa kiểm tra được không chứng minh tài khoản không tồn tại.",
                        "en": "This is an evidence page for the selected target. Missing evidence or unchecked sources do not establish that an account does not exist."},
        "schema_version": "2", "case_id": case_id, "target_id": view.seed.id,
        "question": question, "identity_verified": False,
        "snapshot": snapshot,
        "counts": {"evidence": len(observations), "findings": len(view.finding_entities),
                   "assertions": len(view.assertions), "tasks": len(tasks)},
        "evidence": [{"id": o.id, "run_id": o.run_id, "type": o.observable_type,
                      "entity_id": entity_ids.get((o.observable_type, o.namespace, o.canonical_value)),
                      "value": o.canonical_value[:512], "namespace": o.namespace[:128],
                      "provider": o.provider_id, "observed_at": o.created_at.isoformat()}
                     for o in page],
        "next_cursor": make_cursor(snapshot, page[-1].id) if page and start + len(page) < len(observations) else None,
        "more": start + len(page) < len(observations),
        "history": [{"task_id": t.id, "run_id": t.run_id, "provider": t.provider_id,
                     "status": t.status} for t in history_page],
        "history_next_cursor": make_cursor(snapshot, history_page[-1].id) if history_page and history_start + len(history_page) < len(tasks) else None,
        "history_truncated": history_start + len(history_page) < len(tasks),
        "unknowns": {"noncompleted_tasks": unresolved,
                     "unscoped_observations": view.excluded_unscoped,
                     "source_independence": "NOT_YET_VERIFIED"},
        "question_state": question_state,
        "reasoning": {"ownership_hypotheses": evidence_analysis["ownership_hypotheses"][:20],
                      "link_proofs": evidence_analysis["link_proofs"][:20],
                      "next_best_action": evidence_analysis["next_best_action"],
                      "truncated": (len(evidence_analysis["ownership_hypotheses"]) > 20 or
                                    len(evidence_analysis["link_proofs"]) > 20)},
        "next_action": {"action": "REVIEW_TASK_OUTCOMES" if unresolved else "REVIEW_EVIDENCE",
                        "basis": "noncompleted_tasks" if unresolved else "collected_evidence",
                        "dispatch": False},
    }


async def get_evidence(session, case_id, target_id, observation_id):
    if not target_id:
        raise ValueError("target_id is required")
    view = await project(session, case_id, target_id)
    observation = next((o for o in view.evidence_observations if o.id == observation_id), None)
    if observation is None:
        raise ValueError("Evidence does not belong to selected target")
    entity_id = next((e.id for e in view.entities if (e.observable_type, e.namespace, e.canonical_name) ==
        (observation.observable_type, observation.namespace, observation.canonical_value)), None)
    from spider.service.reporting import evidence_note
    return {"reader_note": {lang: evidence_note(lang) for lang in ("vi", "en")},
            "id": observation.id, "entity_id": entity_id, "type": observation.observable_type,
            "value": observation.canonical_value[:512], "namespace": observation.namespace[:128],
            "provider": observation.provider_id, "provider_version": observation.provider_version,
            "adapter_version": observation.adapter_version,
            "source_family": (observation.upstream_family or "")[:128],
            "run_id": observation.run_id,
            "task_id": observation.task_id, "seed_id": observation.seed_id,
            "observed_at": observation.created_at.isoformat(),
            "artifact_sha256": observation.raw_artifact_sha256,
            "parent_type": observation.parent_observable_type,
            "parent_namespace": (observation.parent_namespace or "")[:128],
            "parent_value": (observation.parent_observable_value or "")[:512],
            "identity_verified": False, "raw_payload_included": False}


async def case_delta(session, case_id, target_id, since_snapshot, question="all", limit=20,
                     after=None, snapshot=None):
    """Return evidence appended after a prior digest snapshot, never inferred absence."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    view = await project(session, case_id, target_id, question)
    if view.seed is None:
        raise ValueError("Select a target for this case")
    previous = read_snapshot(since_snapshot, "case_digest", case_id, view.seed.id, question)
    observations = sorted(view.evidence_observations, key=lambda o: (_stamp(o.created_at), o.id))
    if snapshot is None:
        snapshot = make_snapshot("case_delta", case_id, view.seed.id, question, {
            "from": previous.get("evidence"),
            "to": [_stamp(observations[-1].created_at), observations[-1].id] if observations else None,
        })
    bounds = read_snapshot(snapshot, "case_delta", case_id, view.seed.id, question)
    if bounds.get("from") != previous.get("evidence"):
        raise ValueError("Delta snapshot does not match baseline")
    rows = [o for o in observations if _within_bound(o, "created_at", bounds.get("to")) and
            (bounds.get("from") is None or (_stamp(o.created_at), o.id) > tuple(bounds["from"]))]
    start = 0
    if after is not None:
        after_id = read_cursor(after, snapshot)
        positions = {o.id: i for i, o in enumerate(rows)}
        if after_id not in positions:
            raise ValueError("Cursor does not belong to selected delta")
        start = positions[after_id] + 1
    page = rows[start:start + limit]
    return {"schema_version": "2", "case_id": case_id, "target_id": view.seed.id,
            "question": question, "snapshot": snapshot, "since_snapshot": since_snapshot,
            "label": "FACT", "absence_verified": False,
            "explanation": {"vi": "Đây là bằng chứng mới được ghi nhận sau snapshot trước đó. Việc không có mục trong trang này không chứng minh nguồn không có dữ liệu.",
                            "en": "This lists evidence recorded after the previous snapshot. No item here does not prove a source has no data."},
            "counts": {"new_evidence": len(rows)},
            "evidence": [{"id": o.id, "run_id": o.run_id, "type": o.observable_type,
                          "value": o.canonical_value[:512], "namespace": o.namespace[:128],
                          "provider": o.provider_id, "observed_at": o.created_at.isoformat()} for o in page],
            "next_cursor": make_cursor(snapshot, page[-1].id) if page and start + len(page) < len(rows) else None,
            "more": start + len(page) < len(rows), "identity_verified": False}
