"""Offline phone metadata, never a reverse lookup or proof of assignment."""
import re
import phonenumbers as pn
from phonenumbers import carrier


def phone_metadata(value: str, region="VN") -> dict:
    if not isinstance(value, str) or not re.fullmatch(r"[+0-9 ().-]{7,32}", value.strip()):
        raise ValueError("Invalid phone format")
    try:
        number = pn.parse(value, region)
    except pn.NumberParseException:
        raise ValueError("Invalid phone number") from None
    if number.extension or not pn.is_valid_number(number):
        raise ValueError("Invalid phone number")
    return {"e164": pn.format_number(number, pn.PhoneNumberFormat.E164),
            "region": pn.region_code_for_number(number),
            "number_type": pn.PhoneNumberType.to_string(pn.number_type(number)),
            "original_allocation": carrier.name_for_number(number, "en") or None,
            "current_carrier": "UNKNOWN", "assignment_verified": False,
            "metadata_version": pn.__version__}


def canonical_phone(value: str, supplied: str = "") -> str:
    """An explicitly supplied canonical value cannot override the original number."""
    expected = phone_metadata(value)["e164"]
    if supplied and phone_metadata(supplied)["e164"] != expected:
        raise ValueError("Phone canonical value does not match original input")
    return expected
