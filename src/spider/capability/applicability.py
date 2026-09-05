"""Single fail-closed provider applicability decision used by planning and execution."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ApplicabilityDecision:
    applicable: bool
    reason: str


def assess_provider(adapter, observable_type, capability_name: str) -> ApplicabilityDecision:
    if adapter is None:
        return ApplicabilityDecision(False, "PROVIDER_NOT_REGISTERED")
    try:
        if observable_type not in adapter.accepts():
            return ApplicabilityDecision(False, "UNSUPPORTED_INPUT_TYPE")
        if capability_name not in adapter.capabilities():
            return ApplicabilityDecision(False, "CAPABILITY_CONTRACT_MISMATCH")
    except Exception:
        return ApplicabilityDecision(False, "INVALID_PROVIDER_CONTRACT")
    return ApplicabilityDecision(True, "APPLICABLE")
