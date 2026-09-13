"""Versioned, deterministic assertion-rule registry."""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from spider.models.enums import ObservableType, AssertionType


class AssertionRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Z0-9_]{3,64}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    source_types: list[ObservableType] = Field(min_length=1)
    target_types: list[ObservableType] = Field(min_length=1)
    assertion_type: AssertionType
    evidence_requirement: str = Field(pattern=r"^DIRECT_OBSERVATION$")
    metadata_requirements: dict[str, list[str]] = Field(default_factory=dict)
    fallback: bool = False

    @model_validator(mode="after")
    def validate_metadata_requirements(self):
        if self.fallback and self.metadata_requirements:
            raise ValueError("Fallback rule cannot require metadata")
        for key, values in self.metadata_requirements.items():
            if (not key or len(key) > 64 or not key.replace("_", "").isalnum()
                    or not values or len(values) > 20
                    or any(not isinstance(value, str) or not value or len(value) > 96
                           for value in values)):
                raise ValueError("Invalid rule metadata requirement")
        return self


class RuleFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    registry_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    rules: list[AssertionRule] = Field(min_length=1)


@dataclass(frozen=True)
class RuleDecision:
    assertion_type: AssertionType
    rule_id: str
    rule_version: str
    registry_version: str
    evidence_requirement: str
    metadata_requirements: dict[str, tuple[str, ...]]


class AssertionRuleRegistry:
    def __init__(self, path: str | Path | None = None):
        path = Path(path) if path else Path(__file__).resolve().parents[3] / "config" / "reasoning_rules.yaml"
        payload = RuleFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        self.version = payload.registry_version
        self._rules = {}
        self._fallback = None
        for rule in payload.rules:
            if rule.fallback:
                if self._fallback is not None:
                    raise ValueError("Only one fallback assertion rule is allowed")
                self._fallback = rule
                continue
            for source in rule.source_types:
                for target in rule.target_types:
                    key = (source, target)
                    if key in self._rules:
                        raise ValueError(f"Conflicting assertion rules for {source.value}->{target.value}")
                    self._rules[key] = rule
        if self._fallback is None:
            raise ValueError("A fallback assertion rule is required")

    def resolve(self, source_type: ObservableType, target_type: ObservableType,
                evidence_metadata=None) -> RuleDecision:
        rule = self._rules.get((source_type, target_type))
        evidence_metadata = evidence_metadata if isinstance(evidence_metadata, dict) else {}
        if rule is None or any(evidence_metadata.get(key) not in allowed
                               for key, allowed in rule.metadata_requirements.items()):
            rule = self._fallback
        return RuleDecision(rule.assertion_type, rule.id, rule.version,
                            self.version, rule.evidence_requirement,
                            {key: tuple(values) for key, values in rule.metadata_requirements.items()})


_DEFAULT_REGISTRY = AssertionRuleRegistry()


def resolve_assertion_rule(source_type: ObservableType, target_type: ObservableType,
                           evidence_metadata=None) -> RuleDecision:
    return _DEFAULT_REGISTRY.resolve(source_type, target_type, evidence_metadata)


def infer_assertion_type(source_type: ObservableType, target_type: ObservableType,
                         evidence_metadata=None) -> Optional[AssertionType]:
    """Compatibility API; all pairs resolve through the explicit fallback rule."""
    return resolve_assertion_rule(source_type, target_type, evidence_metadata).assertion_type
