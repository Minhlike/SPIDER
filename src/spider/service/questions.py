"""Versioned target questions and deterministic unresolved-gap projection."""
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from spider.models.enums import ObservableType


class QuestionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Z0-9_]{3,96}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    input_types: list[ObservableType] = Field(min_length=1)
    answer_entity_types: list[ObservableType] = Field(min_length=1)
    next_capabilities: list[str] = Field(min_length=1)


class QuestionFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    registry_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    questions: list[QuestionDefinition] = Field(min_length=1)


class QuestionRegistry:
    def __init__(self, path=None):
        path = Path(path) if path else Path(__file__).resolve().parents[3] / "config" / "investigation_questions.yaml"
        payload = QuestionFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        ids = [question.id for question in payload.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("Question IDs must be unique")
        capability_path = path.with_name("capabilities.yaml")
        if capability_path.exists():
            capabilities = (yaml.safe_load(capability_path.read_text(encoding="utf-8")) or {}).get("capabilities", {})
            unknown = sorted({capability for question in payload.questions
                              for capability in question.next_capabilities
                              if capability not in capabilities})
            if unknown:
                raise ValueError(f"Unknown question capabilities: {', '.join(unknown)}")
        self.version = payload.registry_version
        self.questions = tuple(payload.questions)

    def for_input(self, observable_type):
        kind = ObservableType(observable_type)
        return tuple(question for question in self.questions if kind in question.input_types)


DEFAULT_QUESTIONS = QuestionRegistry()


def assess_questions(view, tasks, registry=DEFAULT_QUESTIONS):
    if view.seed is None:
        return {"registry_version": registry.version, "questions": [], "unresolved_gaps": []}
    finding_by_type = {}
    for entity in view.finding_entities:
        finding_by_type.setdefault(entity.observable_type, []).append(entity.id)
    noncompleted = any(task.status not in {"COMPLETED", "SUCCESS"} for task in tasks)
    attempted = bool(tasks)
    results, gaps = [], []
    for question in registry.for_input(view.seed.observable_type):
        entity_ids = sorted({entity_id for kind in question.answer_entity_types
                             for entity_id in finding_by_type.get(kind.value, [])})
        if entity_ids:
            status, reason = "ANSWERED", "RELEVANT_EVIDENCE_AVAILABLE"
        elif noncompleted:
            status, reason = "UNKNOWN", "COLLECTION_INCOMPLETE"
        elif attempted:
            status, reason = "UNKNOWN", "NO_RELEVANT_EVIDENCE_OBSERVED"
        else:
            status, reason = "OPEN", "NO_COLLECTION_ATTEMPT"
        row = {"id": question.id, "version": question.version, "status": status,
               "reason": reason, "answer_entity_ids": entity_ids,
               "next_capabilities": question.next_capabilities if status != "ANSWERED" else [],
               "absence_verified": False}
        results.append(row)
        if status != "ANSWERED":
            gaps.append({"question_id": question.id, "reason": reason,
                         "next_capabilities": question.next_capabilities})
    return {"registry_version": registry.version, "questions": results,
            "unresolved_gaps": gaps}
