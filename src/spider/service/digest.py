"""Compact, read-only evidence pages. No provider dispatch or raw payload export."""
from sqlalchemy import select

from spider.service.projection import project
from spider.storage.schema import CaseRecord, TaskRunRecord


async def case_digest(session, case_id, target_id=None, question="all", limit=20, after=None):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    if await session.get(CaseRecord, case_id) is None:
        raise ValueError("Case not found")
    view = await project(session, case_id, target_id, question)
    if view.seed is None:
        raise ValueError("Select a target for this case")
    observations = sorted(view.evidence_observations, key=lambda o: (o.created_at, o.id))
    start = 0
    if after is not None:
        positions = {o.id: i for i, o in enumerate(observations)}
        if after not in positions:
            raise ValueError("Cursor does not belong to selected evidence")
        start = positions[after] + 1
    page = observations[start:start + limit]
    tasks = list((await session.scalars(select(TaskRunRecord).where(
        TaskRunRecord.case_id == case_id).order_by(
        TaskRunRecord.started_at.desc(), TaskRunRecord.id))).all())
    tasks = [t for t in tasks if (t.metadata_json or {}).get("seed_id") == view.seed.id]
    unresolved = sum(t.status != "COMPLETED" for t in tasks)
    return {
        "explanation": {"vi": "Đây là trang bằng chứng của mục tiêu đã chọn. Bằng chứng còn thiếu hoặc nguồn chưa kiểm tra được không chứng minh tài khoản không tồn tại.",
                        "en": "This is an evidence page for the selected target. Missing evidence or unchecked sources do not establish that an account does not exist."},
        "schema_version": "1", "case_id": case_id, "target_id": view.seed.id,
        "question": question, "identity_verified": False,
        "counts": {"evidence": len(observations), "findings": len(view.finding_entities),
                   "assertions": len(view.assertions), "tasks": len(tasks)},
        "evidence": [{"id": o.id, "run_id": o.run_id, "type": o.observable_type,
                      "value": o.canonical_value[:512], "namespace": o.namespace[:128],
                      "provider": o.provider_id, "observed_at": o.created_at.isoformat()}
                     for o in page],
        "next_cursor": page[-1].id if page and start + len(page) < len(observations) else None,
        "more": start + len(page) < len(observations),
        "history": [{"task_id": t.id, "run_id": t.run_id, "provider": t.provider_id,
                     "status": t.status} for t in tasks[:limit]],
        "history_truncated": len(tasks) > limit,
        "unknowns": {"noncompleted_tasks": unresolved,
                     "unscoped_observations": view.excluded_unscoped,
                     "source_independence": "NOT_YET_VERIFIED"},
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
    from spider.service.reporting import evidence_note
    return {"reader_note": {lang: evidence_note(lang) for lang in ("vi", "en")},
            "id": observation.id, "type": observation.observable_type,
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
