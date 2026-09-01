import pytest
from spider.resolution.rules import infer_assertion_type
from spider.models.enums import ObservableType, AssertionType

def test_conservative_username_resolution():
    """
    Rule 6 invariant: Never automatically assume SAME_PERSON from matching usernames.
    Matching username -> account emits SHARES_USERNAME.
    Matching account -> account emits POSSIBLY_SAME_IDENTITY.
    """
    # Username to Account
    asrt1 = infer_assertion_type(ObservableType.USERNAME, ObservableType.ACCOUNT)
    assert asrt1 == AssertionType.SHARES_USERNAME
    assert asrt1 != "SAME_PERSON"

    # Account to Account
    asrt2 = infer_assertion_type(ObservableType.ACCOUNT, ObservableType.ACCOUNT)
    assert asrt2 == AssertionType.POSSIBLY_SAME_IDENTITY
    assert asrt2 != "SAME_PERSON"
