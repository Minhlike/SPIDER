import pytest

from spider.capability.scopes import capability_allowed, resolve_investigation_mode
from spider.models.enums import InvestigationMode, ObservableType


def test_email_and_username_default_to_personal_footprint():
    assert resolve_investigation_mode([ObservableType.EMAIL]) == InvestigationMode.PERSONAL_FOOTPRINT
    assert resolve_investigation_mode([ObservableType.USERNAME], "AUTO") == InvestigationMode.PERSONAL_FOOTPRINT
    assert capability_allowed(InvestigationMode.PERSONAL_FOOTPRINT, ObservableType.EMAIL,
                              "EMAIL_PUBLIC_PROFILE_LOOKUP")
    assert not capability_allowed(InvestigationMode.PERSONAL_FOOTPRINT, ObservableType.EMAIL,
                                  "DNS_ENUMERATION")
    assert not capability_allowed(InvestigationMode.PERSONAL_FOOTPRINT, ObservableType.USERNAME,
                                  "BROAD_OSINT")


def test_infrastructure_mode_excludes_personal_discovery_capabilities():
    mode = resolve_investigation_mode([ObservableType.DOMAIN])
    assert mode == InvestigationMode.INFRASTRUCTURE
    assert capability_allowed(mode, ObservableType.DOMAIN, "DNS_ENUMERATION")
    assert not capability_allowed(mode, ObservableType.DOMAIN, "PUBLIC_PROFILE_LOOKUP")


def test_personal_mode_rejects_incompatible_target_before_run():
    with pytest.raises(ValueError):
        resolve_investigation_mode([ObservableType.DOMAIN], "PERSONAL_FOOTPRINT")
