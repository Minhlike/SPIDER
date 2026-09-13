"""Deterministic public-phone candidate projection.

This module never performs a reverse lookup.  It ranks only structured public
mentions already collected as observations, and it deliberately returns
candidate facts rather than an asserted subscriber or owner.
"""
from collections import defaultdict
from urllib.parse import urlsplit

from spider.service.evidence_analysis import public_url


EVIDENCE_CLASSES = {
    "PUBLIC_SELF_PUBLISHED", "THIRD_PARTY_MENTION", "BUSINESS_CONTACT",
    "DIRECTORY_ENTRY", "SEARCH_SNIPPET", "USER_CONFIRMED",
}
FIELDS = {
    "candidate_name": "NAME", "candidate_account": "ACCOUNT",
    "candidate_organization": "ORGANIZATION", "candidate_url": "URL",
    "candidate_location_text": "LOCATION_TEXT",
}
QUALITY = {"PUBLIC_SELF_PUBLISHED": 5, "BUSINESS_CONTACT": 4,
           "THIRD_PARTY_MENTION": 3, "DIRECTORY_ENTRY": 2,
           "SEARCH_SNIPPET": 1, "USER_CONFIRMED": 5}
CLASS_LABELS_VI = {
    "PUBLIC_SELF_PUBLISHED": "Thông tin công khai trên trang của tài khoản",
    "THIRD_PARTY_MENTION": "Số được một bên khác nhắc tới",
    "BUSINESS_CONTACT": "Thông tin liên hệ doanh nghiệp",
    "DIRECTORY_ENTRY": "Mục trong danh bạ công khai",
    "SEARCH_SNIPPET": "Kết quả tìm kiếm chưa mở lại được",
    "USER_CONFIRMED": "Thông tin người dùng đã xác nhận",
}


def _text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def _mention_phone(raw):
    # Collectors must emit the normalized literal that was actually present;
    # this function does not scan arbitrary text or infer a phone relation.
    return raw.get("phone_e164") if isinstance(raw, dict) else None


def _candidate_key(kind, value):
    if kind == "URL":
        return public_url(value)
    return " ".join(value.split()).casefold()


def _source_host(url):
    try:
        return (urlsplit(url).hostname or "").casefold()
    except (TypeError, ValueError):
        return ""


def public_phone_candidates(observations, phone):
    groups = defaultdict(list)
    for observation in observations:
        raw = observation.raw_data_json if isinstance(observation.raw_data_json, dict) else {}
        if _mention_phone(raw) != phone:
            continue
        evidence_class = raw.get("evidence_class")
        if evidence_class not in EVIDENCE_CLASSES:
            continue
        source_url = public_url(raw.get("source_url") or raw.get("profile_url"))
        origin = _text(raw.get("origin_evidence_id"), 128)
        for field, kind in FIELDS.items():
            value = _text(raw.get(field), 512)
            if kind == "URL":
                value = public_url(value)
            if not value:
                continue
            key = (kind, _candidate_key(kind, value))
            groups[key].append({"observation_id": observation.id, "evidence_class": evidence_class,
                                "value": value,
                                "source_url": source_url, "origin": origin,
                                "source_host": _source_host(source_url),
                                "source_date": _text(raw.get("source_date"), 64),
                                "mirror_of": _text(raw.get("mirror_of"), 128),
                                "observed_at": observation.created_at.isoformat()})

    candidates = []
    for (kind, _normalized), rows in groups.items():
        value = rows[0]["value"]
        classes = sorted({row["evidence_class"] for row in rows})
        origins = {row["origin"] for row in rows if row["origin"]}
        source_hosts = {row["source_host"] for row in rows
                        if row["source_host"] and not row["mirror_of"]}
        mirrors = sum(bool(row["mirror_of"]) for row in rows)
        best = max((QUALITY[row["evidence_class"]] for row in rows), default=0)
        latest = max(row["observed_at"] for row in rows)
        best_class = max(classes, key=lambda item: QUALITY[item])
        source_dates = sorted({row["source_date"] for row in rows if row["source_date"]})
        candidates.append({"type": kind, "value": value, "evidence_ids": sorted({row["observation_id"] for row in rows}),
                           "evidence_classes": classes, "first_seen": min(row["observed_at"] for row in rows),
                           "last_seen": latest, "independence": "EXPLICIT_ORIGIN" if origins else "NOT_YET_VERIFIED",
                           "source_urls": sorted({row["source_url"] for row in rows if row["source_url"]})[:20],
                           "source_hosts": sorted(source_hosts)[:20],
                           "source_count": len(source_hosts),
                           "source_dates": source_dates[:20],
                           "freshness": "SOURCE_DATE_REPORTED" if source_dates else "CAPTURE_TIME_ONLY",
                           "rank_reasons": [f"best_public_evidence={best_class}",
                                            f"evidence_count={len(rows)}", f"mirror_mentions={mirrors}",
                                            f"distinct_source_hosts={len(source_hosts)}",
                                            "recency=source_date" if source_dates else "recency=captured_at"],
                           "rank_explanation_vi": (
                               f"Ưu tiên vì: {CLASS_LABELS_VI[best_class].lower()}; "
                               f"có {len(rows)} bằng chứng từ {len(source_hosts)} website; "
                               f"ghi nhận gần nhất {latest}."),
                           "_sort": (best, len(source_hosts), latest, value.casefold())})
    candidates.sort(key=lambda item: item.pop("_sort"), reverse=True)
    contradictions = []
    for kind in sorted({kind for kind, _ in groups}):
        values = sorted({rows[0]["value"] for (candidate_kind, _), rows in groups.items()
                         if candidate_kind == kind}, key=str.casefold)
        if len(values) > 1:
            contradictions.append({"type": kind, "values": values[:20], "state": "COMPETING_PUBLIC_CANDIDATES"})
    named = [candidate for candidate in candidates if candidate["type"] != "URL"]
    snippets = sum("SEARCH_SNIPPET" in candidate["evidence_classes"] for candidate in candidates)
    unknowns = (["NO_PUBLIC_PHONE_MENTION"] if not candidates else
                ["NO_NAMED_PUBLIC_IDENTITY_CANDIDATE"] if not named else [])
    return {"label": "OBSERVATION", "phone": phone, "candidates": candidates[:100],
            "contradictions": contradictions[:20],
            "summary": {"named_candidates": len(named), "public_links": len(candidates),
                        "search_snippets": snippets},
            "unknowns": unknowns,
            "next_action": {"action": "REVIEW_PUBLIC_EVIDENCE" if named else
                                      "VERIFY_SEARCH_LEADS" if candidates else "COLLECT_PUBLIC_EVIDENCE",
                            "dispatch": False, "cost_estimate": "UNKNOWN"},
            "identity_verified": False,
            "reader_note": {"vi": "Đây là các liên hệ công khai với số điện thoại, không phải kết luận về chủ thuê bao.",
                            "en": "These are public links to the phone number, not a conclusion about its subscriber."}}
