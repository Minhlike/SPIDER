import pytest
import phonenumbers as pn
from spider.models.phone import phone_metadata
from spider.models.classifier import TargetClassifier, ClassificationError
from spider.models.observable import NormalizedObservable
from spider.models.enums import ObservableType as T


def test_vietnam_offline_example_normalization_and_portability():
    number = pn.example_number_for_type("VN", pn.PhoneNumberType.MOBILE)
    local = pn.format_number(number, pn.PhoneNumberFormat.NATIONAL)
    expected = pn.format_number(number, pn.PhoneNumberFormat.E164)
    result = TargetClassifier.resolve(local, T.PHONE)
    international = "(+84) " + expected.removeprefix("+84")
    assert TargetClassifier.resolve(international).canonical_value == expected
    assert result.raw_input == local and result.canonical_value == expected
    assert NormalizedObservable(type=T.PHONE, value=local).canonical_value == expected
    metadata = phone_metadata(local)
    assert metadata["number_type"] == "MOBILE"
    assert metadata["current_carrier"] == "UNKNOWN" and not metadata["assignment_verified"]


def test_numeric_input_still_needs_explicit_intent():
    number = pn.example_number_for_type("VN", pn.PhoneNumberType.MOBILE)
    local = pn.format_number(number, pn.PhoneNumberFormat.NATIONAL).replace(" ", "")
    with pytest.raises(ClassificationError):
        TargetClassifier.resolve(local)


@pytest.mark.parametrize("value", ["+840123", "call me +84912345678", "+84912345678 ext 2", "090xyz1234"])
def test_invalid_phone_is_not_guessed(value):
    with pytest.raises(ValueError):
        phone_metadata(value)


def test_ipv6_canonical_identity():
    assert NormalizedObservable(type=T.IPV6_ADDRESS, value="2001:4860:0000:0:0:0:0:8888").canonical_value == "2001:4860::8888"


def test_supplied_phone_canonical_value_cannot_bypass_normalization():
    from spider.models.target import Target
    mobile = pn.format_number(pn.example_number_for_type("VN", pn.PhoneNumberType.MOBILE), pn.PhoneNumberFormat.NATIONAL)
    fixed = pn.format_number(pn.example_number_for_type("VN", pn.PhoneNumberType.FIXED_LINE), pn.PhoneNumberFormat.E164)
    expected = phone_metadata(mobile)["e164"]
    assert Target(case_id="fixture", observable_type=T.PHONE, raw_input=mobile, canonical_value=mobile).canonical_value == expected
    for factory in (
        lambda: Target(case_id="fixture", observable_type=T.PHONE, raw_input=mobile, canonical_value=fixed),
        lambda: NormalizedObservable(type=T.PHONE, value=mobile, canonical_value=fixed),
        lambda: NormalizedObservable(type=T.PHONE, value="not-a-phone", canonical_value=fixed),
    ):
        with pytest.raises(ValueError):
            factory()
