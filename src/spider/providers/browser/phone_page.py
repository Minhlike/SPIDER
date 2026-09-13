"""Extract bounded, public phone-link evidence from an already opened page.

The extractor never guesses a subscriber.  A candidate is emitted only when the
same page visibly contains the requested phone or a JSON-LD entity declares the
matching telephone value.
"""
from html.parser import HTMLParser
import json
import re
from urllib.parse import unquote, urlsplit

from spider.providers.maigret.profile_metadata import public_metadata


SOCIAL_SOURCES = frozenset({"Facebook", "TikTok", "Telegram", "Zalo"})
DIRECTORY_SOURCES = frozenset({"Trang Vàng Việt Nam"})
ORGANIZATION_TYPES = frozenset({
    "Organization", "LocalBusiness", "ProfessionalService", "Corporation",
    "Store", "Restaurant", "Hotel", "MedicalBusiness", "RealEstateAgent",
    "AutomotiveBusiness", "FinancialService", "LegalService",
})


class JsonLdParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = False
        self.buffer = []
        self.documents = []

    def handle_starttag(self, tag, attrs):
        pairs = dict(attrs)
        if tag == "script" and (pairs.get("type") or "").casefold() == "application/ld+json":
            self.active, self.buffer = True, []

    def handle_data(self, data):
        if self.active:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag != "script" or not self.active:
            return
        self.active = False
        try:
            self.documents.append(json.loads("".join(self.buffer)))
        except (ValueError, TypeError):
            pass


def _text(value, limit=512):
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned[:limit] if cleaned else None


def _types(node):
    value = node.get("@type") if isinstance(node, dict) else None
    return {item for item in ([value] if isinstance(value, str) else value or [])
            if isinstance(item, str)}


def _nodes(document):
    if isinstance(document, list):
        for item in document[:100]:
            if isinstance(item, dict):
                yield item
        return
    if not isinstance(document, dict):
        return
    graph = document.get("@graph")
    if isinstance(graph, list):
        for item in graph[:100]:
            if isinstance(item, dict):
                yield item
    else:
        yield document


def _phones(node):
    values = []
    telephone = node.get("telephone")
    values.extend(telephone if isinstance(telephone, list) else [telephone])
    points = node.get("contactPoint")
    for point in points if isinstance(points, list) else [points]:
        if isinstance(point, dict):
            value = point.get("telephone")
            values.extend(value if isinstance(value, list) else [value])
    return [value for value in values[:25] if isinstance(value, str)]


def _address(node):
    value = node.get("address")
    if isinstance(value, str):
        return _text(value)
    if not isinstance(value, dict):
        return None
    parts = [_text(value.get(field), 160) for field in (
        "streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry")]
    return _text(", ".join(part for part in parts if part))


def _account_from_url(source, page_url):
    if source not in SOCIAL_SOURCES:
        return None
    try:
        parts = [unquote(part) for part in urlsplit(page_url).path.split("/") if part]
    except (TypeError, ValueError):
        return None
    if source == "TikTok" and len(parts) == 1 and parts[0].startswith("@"):
        handle = parts[0][1:]
    elif source == "Telegram" and len(parts) == 1 and parts[0] not in {"s", "share"}:
        handle = parts[0]
    elif source == "Zalo" and len(parts) == 1:
        handle = parts[0]
    elif source == "Facebook" and len(parts) == 1 and parts[0].casefold() not in {
            "login", "share", "watch", "groups", "marketplace"}:
        handle = parts[0]
    else:
        return None
    return f"{handle}@{source.casefold()}" if re.fullmatch(r"[\w.@-]{2,128}", handle) else None


def extract_phone_page_evidence(metadata_html, visible_text, phone, page_url, source,
                                literal_matcher):
    """Return safe structured fields, or an empty dict when the phone is absent."""
    metadata_html = metadata_html if isinstance(metadata_html, str) else ""
    visible = bool(literal_matcher(visible_text, phone))
    parser = JsonLdParser()
    try:
        parser.feed(metadata_html[:524288])
    except (ValueError, AssertionError):
        pass

    matched_nodes = [node for document in parser.documents for node in _nodes(document)
                     if any(literal_matcher(value, phone) for value in _phones(node))]
    if not visible and not matched_nodes:
        return {}

    public = public_metadata(metadata_html)
    result = {
        "phone_e164": phone,
        "candidate_url": page_url,
        "source_url": page_url,
        "literal_basis": "VISIBLE_PAGE_TEXT" if visible else "JSONLD_TELEPHONE",
        "identity_verified": False,
    }
    account = _account_from_url(source, page_url)
    if account:
        result["candidate_account"] = account

    for node in matched_nodes[:20]:
        node_types = _types(node)
        name = _text(node.get("name"), 200)
        if "Person" in node_types and name and "candidate_name" not in result:
            result["candidate_name"] = name
        if node_types & ORGANIZATION_TYPES and name and "candidate_organization" not in result:
            result["candidate_organization"] = name
        address = _address(node)
        if address and "candidate_location_text" not in result:
            result["candidate_location_text"] = address
        source_date = _text(node.get("dateModified") or node.get("datePublished"), 64)
        if source_date and "source_date" not in result:
            result["source_date"] = source_date

    if account and public.get("display_name") and "candidate_name" not in result:
        result["candidate_name"] = public["display_name"]
    if result.get("candidate_organization"):
        evidence_class = "BUSINESS_CONTACT"
    elif source in DIRECTORY_SOURCES:
        evidence_class = "DIRECTORY_ENTRY"
    elif account:
        evidence_class = "PUBLIC_SELF_PUBLISHED"
    else:
        evidence_class = "THIRD_PARTY_MENTION"
    result["evidence_class"] = evidence_class
    result["metadata_basis"] = "public_page_phone_revalidation"
    return result
