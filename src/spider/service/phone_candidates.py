"""Deterministic public-phone candidate projection.

This module never performs a reverse lookup.  It ranks only structured public
mentions already collected as observations, and it deliberately returns
candidate facts rather than an asserted subscriber or owner.
"""
from collections import defaultdict

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


def _text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def _mention_phone(raw):
    # Collectors must emit the normalized literal that was actually present;
    # this function does not scan arbitrary text or infer a phone relation.
    return raw.get("phone_e164") if isinstance(raw, dict) else None


def public_phone_candidates(observations, phone):
    groups, source_values = defaultdict(list), defaultdict(set)
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
            key = (kind, value)
            groups[key].append({"observation_id": observation.id, "evidence_class": evidence_class,
                                "source_url": source_url, "origin": origin,
                                "mirror_of": _text(raw.get("mirror_of"), 128),
                                "observed_at": observation.created_at.isoformat()})
            if source_url:
                source_values[kind].add(value)

    candidates = []
    for (kind, value), rows in groups.items():
        classes = sorted({row["evidence_class"] for row in rows})
        origins = {row["origin"] for row in rows if row["origin"]}
        # Same upstream origin/mirror is one cluster; missing provenance never
        # inflates independence.
        clusters = origins or ({row["source_url"] for row in rows if row["source_url"]} if len(rows) == 1 else set())
        mirrors = sum(bool(row["mirror_of"]) for row in rows)
        best = max((QUALITY[row["evidence_class"]] for row in rows), default=0)
        latest = max(row["observed_at"] for row in rows)
        candidates.append({"type": kind, "value": value, "evidence_ids": sorted({row["observation_id"] for row in rows}),
                           "evidence_classes": classes, "first_seen": min(row["observed_at"] for row in rows),
                           "last_seen": latest, "independence": "EXPLICIT_ORIGIN" if origins else "NOT_YET_VERIFIED",
                           "rank_reasons": [f"best_public_evidence={max(classes, key=lambda item: QUALITY[item])}",
                                            f"evidence_count={len(rows)}", f"mirror_mentions={mirrors}",
                                            f"independent_clusters={len(clusters) if origins else 0}",
                                            "recency=captured_at"],
                           "_sort": (best, len(origins), latest, value.casefold())})
    candidates.sort(key=lambda item: item.pop("_sort"), reverse=True)
    contradictions = []
    for kind in sorted({kind for kind, _ in groups}):
        values = sorted(value for candidate_kind, value in groups if candidate_kind == kind)
        if len(values) > 1:
            contradictions.append({"type": kind, "values": values[:20], "state": "COMPETING_PUBLIC_CANDIDATES"})
    return {"label": "FACT", "phone": phone, "candidates": candidates[:100],
            "contradictions": contradictions[:20],
            "unknowns": [] if candidates else ["NO_PUBLIC_PHONE_MENTION"],
            "next_action": {"action": "REVIEW_PUBLIC_EVIDENCE" if candidates else "COLLECT_PUBLIC_EVIDENCE",
                            "dispatch": False, "cost_estimate": "UNKNOWN"},
            "identity_verified": False,
            "reader_note": {"vi": "Đây là các liên hệ công khai với số điện thoại, không phải kết luận về chủ thuê bao.",
                            "en": "These are public links to the phone number, not a conclusion about its subscriber."}}
