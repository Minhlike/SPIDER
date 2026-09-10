import pytest

from spider.models.enums import AssertionType, ObservableType
from spider.resolution.rules import AssertionRuleRegistry, resolve_assertion_rule


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
