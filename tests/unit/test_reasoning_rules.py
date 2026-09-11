import pytest
from types import SimpleNamespace

from spider.models.enums import AssertionType, ObservableType
from spider.resolution.rules import AssertionRuleRegistry, resolve_assertion_rule
from spider.service.questions import QuestionRegistry, assess_questions


def test_versioned_registry_resolves_specific_and_fallback_rules():
    specific = resolve_assertion_rule(ObservableType.USERNAME, ObservableType.ACCOUNT)
    assert specific.assertion_type == AssertionType.SHARES_USERNAME
    assert specific.rule_id == "USERNAME_ACCOUNT_CANDIDATE"
    assert specific.rule_version == "1.0.0" and specific.registry_version == "1.0.0"
    assert specific.evidence_requirement == "DIRECT_OBSERVATION"

    fallback = resolve_assertion_rule(ObservableType.PHONE, ObservableType.URL)
    assert fallback.assertion_type == AssertionType.ASSOCIATED_WITH
    assert fallback.rule_id == "DIRECT_ASSOCIATION_FALLBACK"


def test_registry_fails_closed_on_conflicting_rules(tmp_path):
    rules = tmp_path / "rules.yaml"
    rules.write_text('''registry_version: "1.0.0"
rules:
  - {id: RULE_ONE, version: "1.0.0", source_types: [EMAIL], target_types: [DOMAIN], assertion_type: BELONGS_TO_DOMAIN, evidence_requirement: DIRECT_OBSERVATION}
  - {id: RULE_TWO, version: "1.0.0", source_types: [EMAIL], target_types: [DOMAIN], assertion_type: ASSOCIATED_WITH, evidence_requirement: DIRECT_OBSERVATION}
  - {id: FALLBACK_RULE, version: "1.0.0", source_types: [RAW_DATA], target_types: [RAW_DATA], assertion_type: ASSOCIATED_WITH, evidence_requirement: DIRECT_OBSERVATION, fallback: true}
''', encoding="utf-8")
    with pytest.raises(ValueError, match="Conflicting assertion rules"):
        AssertionRuleRegistry(rules)


def test_question_registry_requires_evidence_and_capability_coverage_to_answer():
    view = SimpleNamespace(
        seed=SimpleNamespace(observable_type="USERNAME"),
        finding_entities=[SimpleNamespace(observable_type="ACCOUNT", id="account-1")])
    partial = assess_questions(view, [])
    question = partial["questions"][0]
    assert question["status"] == "PARTIAL"
    assert question["reason"] == "EVIDENCE_AVAILABLE_COVERAGE_INCOMPLETE"

    completed = [SimpleNamespace(capability=name, status="COMPLETED")
                 for name in question["next_capabilities"]]
    answered = assess_questions(view, completed)
    question = answered["questions"][0]
    assert question["id"] == "USERNAME_PUBLIC_ACCOUNTS"
    assert question["status"] == "ANSWERED" and question["answer_entity_ids"] == ["account-1"]
    assert question["absence_verified"] is False

    open_state = assess_questions(SimpleNamespace(
        seed=SimpleNamespace(observable_type="EMAIL"), finding_entities=[]), [])
    assert all(row["status"] == "OPEN" for row in open_state["questions"])
    assert all(row["reason"] == "NO_COLLECTION_ATTEMPT" for row in open_state["unresolved_gaps"])

    unrelated = assess_questions(SimpleNamespace(
        seed=SimpleNamespace(observable_type="USERNAME"), finding_entities=[]),
        [SimpleNamespace(capability="DNS_ENUMERATION", status="FAILED")])
    assert unrelated["questions"][0]["status"] == "OPEN"


def test_question_registry_rejects_duplicate_ids(tmp_path):
    questions = tmp_path / "questions.yaml"
    questions.write_text('''registry_version: "1.0.0"
questions:
  - {id: SAME_QUESTION, version: "1.0.0", input_types: [EMAIL], answer_entity_types: [ACCOUNT], next_capabilities: [PUBLIC_PROFILE_LOOKUP]}
  - {id: SAME_QUESTION, version: "1.0.0", input_types: [USERNAME], answer_entity_types: [ACCOUNT], next_capabilities: [PUBLIC_PROFILE_LOOKUP]}
''', encoding="utf-8")
    with pytest.raises(ValueError, match="Question IDs must be unique"):
        QuestionRegistry(questions)
