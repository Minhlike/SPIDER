from collections.abc import Iterable

from spider.models.enums import InvestigationMode, ObservableType


PERSONAL_CAPABILITIES = frozenset({
    "PUBLIC_PROFILE_LOOKUP",
    "EMAIL_PUBLIC_PROFILE_LOOKUP",
    "USERNAME_DISCOVERY",
    "BROWSER_PERSONAL_DISCOVERY",
})

PERSONAL_INPUTS = frozenset({ObservableType.EMAIL, ObservableType.USERNAME})


def resolve_investigation_mode(
    observable_types: Iterable[ObservableType],
    requested: str | InvestigationMode | None = None,
) -> InvestigationMode:
    types = {ObservableType(item) for item in observable_types}
    if requested in (None, "", "AUTO"):
        return (InvestigationMode.PERSONAL_FOOTPRINT
                if types and types <= PERSONAL_INPUTS
                else InvestigationMode.INFRASTRUCTURE)
    mode = InvestigationMode(requested)
    if mode == InvestigationMode.PERSONAL_FOOTPRINT and not types <= PERSONAL_INPUTS:
        raise ValueError("Personal-footprint mode only supports EMAIL or USERNAME targets")
    return mode


def capability_allowed(
    mode: InvestigationMode,
    observable_type: ObservableType,
    capability_name: str,
) -> bool:
    if mode == InvestigationMode.PERSONAL_FOOTPRINT:
        if observable_type == ObservableType.EMAIL:
            return capability_name in {"PUBLIC_PROFILE_LOOKUP", "EMAIL_PUBLIC_PROFILE_LOOKUP",
                                       "BROWSER_PERSONAL_DISCOVERY"}
        if observable_type == ObservableType.USERNAME:
            return capability_name in {"PUBLIC_PROFILE_LOOKUP", "USERNAME_DISCOVERY",
                                       "BROWSER_PERSONAL_DISCOVERY"}
        return False
    return capability_name not in PERSONAL_CAPABILITIES
