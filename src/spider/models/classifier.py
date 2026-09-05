"""Offline syntax classification. A plausible shape is not proof of user intent."""
import ipaddress
import re
from typing import List, Literal
from urllib.parse import urlsplit

import idna
import tldextract
from pydantic import BaseModel
from spider.models.enums import ObservableType as T

# Use the pinned package snapshot: never fetch a suffix list or create a user cache.
_SUFFIXES = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None,
                                include_psl_private_domains=False)


class ClassificationResult(BaseModel):
    detected_type: T
    confidence: float
    confidence_kind: str = "heuristic_not_probability"
    canonical_value: str
    candidate_types: List[T]
    raw_input: str
    needs_confirmation: bool = False
    reason: str
    decision_source: Literal["syntax", "heuristic", "explicit"] = "syntax"


class ClassificationError(ValueError):
    def __init__(self, message, classification=None):
        super().__init__(message)
        self.classification = classification

    def detail(self):
        return {"code": "ambiguous_target" if self.classification else "invalid_target",
                "message": str(self),
                "classification": self.classification.model_dump(mode="json") if self.classification else None}


class TargetClassifier:
    USERNAME_REGEX = re.compile(r"[\w.-]{1,64}\Z")
    EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[^@\s]+\Z")
    ACCOUNT_REGEX = re.compile(r"[a-zA-Z0-9_.-]+@[a-zA-Z0-9_-]+\Z")
    PHONE_REGEX = re.compile(r"\+[1-9]\d{7,14}\Z", re.ASCII)
    ASN_REGEX = re.compile(r"AS([0-9]+)\Z", re.IGNORECASE)

    @classmethod
    def _username(cls, value):
        return bool(cls.USERNAME_REGEX.fullmatch(value) and
                    any(c.isalnum() or c == "_" for c in value))

    @staticmethod
    def _host(value):
        try:
            host = idna.encode(value.removesuffix("."), uts46=True, std3_rules=True).decode("ascii").lower()
            if len(host) > 253:
                return None
            return host
        except (idna.IDNAError, UnicodeError):
            return None

    @classmethod
    def _canonical_for_type(cls, value, kind):
        if kind == T.USERNAME:
            value = value.removeprefix("@")
            if cls._username(value):
                return value
        elif kind in (T.DOMAIN, T.HOSTNAME):
            host = cls._host(value)
            if host and (kind == T.HOSTNAME or "." in host):
                # Explicit intent may refer to an internal/unknown suffix.
                return host
        elif kind == T.EMAIL and cls.EMAIL_REGEX.fullmatch(value):
            local, host = value.rsplit("@", 1)
            host = cls._host(host)
            if host and "." in host:
                return local.lower() + "@" + host
        elif kind == T.ACCOUNT and cls.ACCOUNT_REGEX.fullmatch(value):
            return value.lower()
        elif kind == T.URL:
            try:
                parts = urlsplit(value)
                if (parts.scheme.lower() in ("http", "https") and parts.hostname and
                        not parts.username and not parts.password and
                        not any(c.isspace() for c in value) and "\\" not in value):
                    parts.port  # Validate malformed/out-of-range ports.
                    host = parts.hostname
                    if cls._host(host) or ipaddress.ip_address(host):
                        return value
            except ValueError:
                pass
        elif kind in (T.IP_ADDRESS, T.IPV6_ADDRESS, T.CIDR):
            try:
                item = ipaddress.ip_network(value, strict=False) if kind == T.CIDR else ipaddress.ip_address(value)
                if kind == T.CIDR or item.version == (6 if kind == T.IPV6_ADDRESS else 4):
                    return str(item)
            except ValueError:
                pass
        elif kind == T.ASN:
            match = cls.ASN_REGEX.fullmatch(value)
            if match and 0 <= int(match[1]) <= 4294967295:
                return "AS" + str(int(match[1]))
        elif kind == T.PHONE:
            from spider.models.phone import phone_metadata
            try:
                return phone_metadata(value)["e164"]
            except ValueError:
                pass
        elif (kind == T.ORGANIZATION and 2 <= len(value) <= 256
              and all(ord(c) >= 32 and ord(c) != 127 for c in value)):
            return value
        return None

    @classmethod
    def classify(cls, raw_input: str, target_type: T | str | None = None) -> ClassificationResult:
        if not isinstance(raw_input, str) or not raw_input.strip() or len(raw_input) > 2048:
            raise ClassificationError("Enter a target between 1 and 2048 characters.")
        value = raw_input.strip()
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ClassificationError("Control characters are not allowed in a target.")

        def result(kind, canonical, reason, candidates=None, confirm=False, source="syntax", score=0.99):
            return ClassificationResult(detected_type=kind, canonical_value=canonical,
                raw_input=raw_input, candidate_types=candidates or [kind], confidence=score,
                reason=reason, needs_confirmation=confirm, decision_source=source)

        if target_type is not None:
            try:
                kind = T(target_type)
            except ValueError:
                raise ClassificationError("Unsupported target type.") from None
            canonical = cls._canonical_for_type(value, kind)
            if canonical is None:
                raise ClassificationError("The value does not match the selected type. Select PHONE for Vietnamese national format, or use an international country code.")
            return result(kind, canonical, "explicit_type", source="explicit")

        if value.startswith("@") and cls._username(value[1:]):
            return result(T.USERNAME, value[1:], "username_marker", source="explicit")
        for kind in (T.URL, T.EMAIL, T.ACCOUNT, T.CIDR, T.IP_ADDRESS, T.IPV6_ADDRESS, T.ASN, T.PHONE):
            if kind == T.PHONE and not value.lstrip(" (").startswith("+"):
                continue  # Local numeric input still requires explicit PHONE intent.
            # Avoid interpreting a plain IP as a /32 or /128 network.
            if kind == T.CIDR and "/" not in value:
                continue
            canonical = cls._canonical_for_type(value, kind)
            if canonical is not None:
                return result(kind, canonical, "explicit_syntax")

        host = cls._host(value)
        suffix = _SUFFIXES(host) if host and "." in host else None
        if suffix and suffix.suffix and suffix.domain:
            kind = T.HOSTNAME if suffix.subdomain else T.DOMAIN
            ambiguous = cls._username(value) and not value.endswith(".")
            return result(kind, host, "domain_or_username" if ambiguous else "public_suffix",
                          [kind, T.USERNAME] if ambiguous else [kind], ambiguous,
                          "heuristic", 0.6 if ambiguous else 0.9)
        if cls._username(value):
            numeric = bool(re.fullmatch(r"[0-9]{8,15}", value))
            candidates = [T.USERNAME, T.PHONE] if numeric else [T.USERNAME]
            if host and "." in host:
                candidates.append(T.HOSTNAME)
            return result(T.USERNAME, value,
                          "numeric_identifier" if numeric else "unknown_suffix" if "." in value else "username_shape",
                          candidates, numeric, "heuristic", 0.6 if numeric else 0.8)
        raise ClassificationError("Unrecognized target. Enter an email, username, valid host, IP, URL or international phone number.")

    @classmethod
    def resolve(cls, raw_input: str, target_type: T | str | None = None) -> ClassificationResult:
        result = cls.classify(raw_input, target_type)
        if result.needs_confirmation:
            raise ClassificationError("Choose the target type before starting the investigation.", result)
        return result
