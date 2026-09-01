import re
import ipaddress
from typing import List, Optional
from pydantic import BaseModel
from spider.models.enums import ObservableType

class ClassificationResult(BaseModel):
    detected_type: ObservableType
    confidence: float
    canonical_value: str
    candidate_types: List[ObservableType]
    raw_input: str

class TargetClassifier:
    EMAIL_REGEX = re.compile(
        r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$"
    )
    ASN_REGEX = re.compile(r"^AS(\d+)$", re.IGNORECASE)
    PHONE_REGEX = re.compile(r"^\+?[1-9]\d{7,14}$")
    URL_REGEX = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
    ACCOUNT_REGEX = re.compile(r"^[a-zA-Z0-9_.-]+@[a-zA-Z0-9_-]+$")

    @classmethod
    def classify(cls, raw_input: str) -> ClassificationResult:
        cleaned = raw_input.strip()
        val_lower = cleaned.lower()

        # 1. URL
        if cls.URL_REGEX.match(cleaned):
            return ClassificationResult(
                detected_type=ObservableType.URL,
                confidence=0.99,
                canonical_value=cleaned,
                candidate_types=[ObservableType.URL, ObservableType.DOMAIN],
                raw_input=cleaned
            )

        # 2. EMAIL (Checks full RFC domain extension, e.g. .vn, .io, .com)
        if cls.EMAIL_REGEX.match(cleaned):
            return ClassificationResult(
                detected_type=ObservableType.EMAIL,
                confidence=0.98,
                canonical_value=val_lower,
                candidate_types=[ObservableType.EMAIL],
                raw_input=cleaned
            )

        # 3. ACCOUNT (e.g. user@github, admin@reddit - distinct from email without TLD)
        if "@" in cleaned and cls.ACCOUNT_REGEX.match(cleaned) and "." not in cleaned.split("@")[1]:
            return ClassificationResult(
                detected_type=ObservableType.ACCOUNT,
                confidence=0.95,
                canonical_value=val_lower,
                candidate_types=[ObservableType.ACCOUNT, ObservableType.USERNAME],
                raw_input=cleaned
            )

        # 4. CIDR
        if "/" in cleaned:
            try:
                net = ipaddress.ip_network(cleaned, strict=False)
                return ClassificationResult(
                    detected_type=ObservableType.CIDR,
                    confidence=0.99,
                    canonical_value=str(net),
                    candidate_types=[ObservableType.CIDR],
                    raw_input=cleaned
                )
            except ValueError:
                pass

        # 5. IP Address (IPv4 & IPv6)
        try:
            ip = ipaddress.ip_address(cleaned)
            obs_type = ObservableType.IPV6_ADDRESS if ip.version == 6 else ObservableType.IP_ADDRESS
            return ClassificationResult(
                detected_type=obs_type,
                confidence=0.99,
                canonical_value=str(ip),
                candidate_types=[obs_type],
                raw_input=cleaned
            )
        except ValueError:
            pass

        # 6. ASN (AS15133, AS45899)
        asn_match = cls.ASN_REGEX.match(cleaned)
        if asn_match:
            asn_canonical = f"AS{asn_match.group(1)}"
            return ClassificationResult(
                detected_type=ObservableType.ASN,
                confidence=0.99,
                canonical_value=asn_canonical,
                candidate_types=[ObservableType.ASN],
                raw_input=cleaned
            )

        # 7. Phone Number (E.164, e.g. +84901234567, +14155552671)
        phone_cleaned = re.sub(r"[\s\-\(\)]", "", cleaned)
        if cls.PHONE_REGEX.match(phone_cleaned):
            norm_phone = phone_cleaned if phone_cleaned.startswith("+") else f"+{phone_cleaned}"
            return ClassificationResult(
                detected_type=ObservableType.PHONE,
                confidence=0.90,
                canonical_value=norm_phone,
                candidate_types=[ObservableType.PHONE],
                raw_input=cleaned
            )

        # 8. Domain / Hostname
        if "." in cleaned and not cleaned.startswith(".") and not cleaned.endswith("."):
            parts = cleaned.split(".")
            if len(parts) >= 2 and all(len(p) > 0 for p in parts) and not any(c in cleaned for c in " /\:"):
                # If it has more than 2 labels, consider HOSTNAME candidate
                det_type = ObservableType.DOMAIN if len(parts) == 2 else ObservableType.HOSTNAME
                return ClassificationResult(
                    detected_type=det_type,
                    confidence=0.95,
                    canonical_value=val_lower,
                    candidate_types=[ObservableType.DOMAIN, ObservableType.HOSTNAME],
                    raw_input=cleaned
                )

        # 9. Username default fallback
        return ClassificationResult(
            detected_type=ObservableType.USERNAME,
            confidence=0.80,
            canonical_value=cleaned,
            candidate_types=[ObservableType.USERNAME, ObservableType.ORGANIZATION],
            raw_input=cleaned
        )
