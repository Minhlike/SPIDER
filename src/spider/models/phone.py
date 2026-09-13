"""Offline phone metadata, never a reverse lookup or proof of assignment."""
import re
import phonenumbers as pn
from phonenumbers import carrier


NUMBER_TYPE_VI = {
    "MOBILE": "Di động", "FIXED_LINE": "Điện thoại cố định",
    "FIXED_LINE_OR_MOBILE": "Cố định hoặc di động", "TOLL_FREE": "Miễn cước",
    "PREMIUM_RATE": "Tính cước cao", "VOIP": "Điện thoại Internet (VoIP)",
    "SHARED_COST": "Chia sẻ cước", "PERSONAL_NUMBER": "Số cá nhân",
    "PAGER": "Máy nhắn tin", "UAN": "Số truy cập chung", "VOICEMAIL": "Hộp thư thoại",
    "UNKNOWN": "Chưa xác định",
}


def phone_metadata(value: str, region="VN") -> dict:
    if not isinstance(value, str) or not re.fullmatch(r"[+0-9 ().-]{7,32}", value.strip()):
        raise ValueError("Invalid phone format")
    try:
        number = pn.parse(value, region)
    except pn.NumberParseException:
        raise ValueError("Invalid phone number") from None
    if number.extension or not pn.is_valid_number(number):
        raise ValueError("Invalid phone number")
    number_type = pn.PhoneNumberType.to_string(pn.number_type(number))
    national_digits = str(number.national_number)
    original_allocation = (carrier.name_for_number(number, "vi")
                           or carrier.name_for_number(number, "en") or None)
    return {"e164": pn.format_number(number, pn.PhoneNumberFormat.E164),
            "national_format": pn.format_number(number, pn.PhoneNumberFormat.NATIONAL),
            "country_calling_code": number.country_code,
            "region": pn.region_code_for_number(number),
            "number_type": number_type,
            "number_type_label_vi": NUMBER_TYPE_VI.get(number_type, "Chưa xác định"),
            "detected_prefix": ("0" + national_digits[:2]
                                if number.country_code == 84 and number_type == "MOBILE" else None),
            "original_allocation": original_allocation,
            "current_carrier": "UNKNOWN", "assignment_verified": False,
            "metadata_version": pn.__version__}


def canonical_phone(value: str, supplied: str = "") -> str:
    """An explicitly supplied canonical value cannot override the original number."""
    expected = phone_metadata(value)["e164"]
    if supplied and phone_metadata(supplied)["e164"] != expected:
        raise ValueError("Phone canonical value does not match original input")
    return expected
