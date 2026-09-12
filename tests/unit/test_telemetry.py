from spider.service.investigation_api import _reliability_band, _task_signal_codes
from spider.models.budget import BudgetLedger, ExecutionBudget
from spider.models.enums import ObservableType
from spider.models.observable import NormalizedObservable


def test_telemetry_reads_structured_rate_and_timeout_signals_only():
    codes = _task_signal_codes({
        "coverage": {"priority_sites": {
            "one": {"outcome": "HTTP_429"},
            "two": {"reason": "TIMEOUT"},
        }},
        "untrusted_message": "RATE_LIMIT must not be mined from prose",
    })
    assert codes == {"HTTP_429", "TIMEOUT"}


def test_reliability_is_fail_closed_until_sample_and_accounting_gate():
    assert _reliability_band(19, 0, 0, 0, 0, True) == "NOT_YET_CALIBRATED"
    assert _reliability_band(20, 0, 0, 0, 0, False) == "NOT_YET_CALIBRATED"
    assert _reliability_band(20, .05, 0, .05, 0, True) == "OBSERVED_HIGH"
    assert _reliability_band(20, .2, .1, .05, .05, True) == "OBSERVED_MEDIUM"
    assert _reliability_band(20, .3, .2, .1, .1, True) == "OBSERVED_LOW"


def test_entity_admission_reports_novelty_atomically():
    ledger, budget = BudgetLedger(), ExecutionBudget(max_entities=1)
    first = NormalizedObservable(type=ObservableType.USERNAME, value="fixture")
    other = NormalizedObservable(type=ObservableType.USERNAME, value="other")
    assert ledger.admit_entity_with_novelty(budget, "case", first) == (True, True)
    assert ledger.admit_entity_with_novelty(budget, "case", first) == (True, False)
    assert ledger.admit_entity_with_novelty(budget, "case", other) == (False, False)
    assert ledger.entities_count == 1 and ledger.entities_rejected_count == 1
