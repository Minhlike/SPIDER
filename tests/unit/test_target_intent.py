import pytest

from spider.models.classifier import TargetClassifier, ClassificationError
from spider.models.enums import ObservableType as T


@pytest.mark.parametrize("value", ["ms.orianawren", "le_mai_linh2002", "first.last", "name_with.dot", "alice..smith", "-alice.com"])
def test_dots_do_not_imply_domains(value):
    result = TargetClassifier.resolve(value)
    assert result.detected_type == T.USERNAME
    assert result.canonical_value == value
    assert result.confidence_kind == "heuristic_not_probability"


@pytest.mark.parametrize("value,kind", [("example.com", T.DOMAIN), ("corp.co.uk", T.DOMAIN),
    ("sub.example.com", T.HOSTNAME), ("alice.dev", T.DOMAIN), ("食狮.公司.cn", T.DOMAIN)])
def test_public_suffix_boundary_is_only_a_suggestion(value, kind):
    result = TargetClassifier.classify(value)
    assert result.detected_type == kind
    assert result.needs_confirmation
    assert T.USERNAME in result.candidate_types
    with pytest.raises(ClassificationError) as error:
        TargetClassifier.resolve(value)
    assert error.value.detail()["code"] == "ambiguous_target"
    assert TargetClassifier.resolve(value, kind).decision_source == "explicit"
    assert TargetClassifier.resolve(value, T.USERNAME).canonical_value == value


@pytest.mark.parametrize("value,kind,canonical", [
    ("@ms.orianawren", T.USERNAME, "ms.orianawren"),
    ("@Mixed.Case", T.USERNAME, "Mixed.Case"),
    ("EXAMPLE.COM.", T.DOMAIN, "example.com"),
    ("https://example.com/profile", T.URL, "https://example.com/profile"),
    ("2001:db8::1", T.IPV6_ADDRESS, "2001:db8::1"),
    ("+84 901-234-567", T.PHONE, "+84901234567"),
])
def test_explicit_syntax(value, kind, canonical):
    result = TargetClassifier.resolve(value)
    assert result.detected_type == kind
    assert result.canonical_value == canonical


def test_numeric_username_does_not_invent_a_country_code():
    result = TargetClassifier.classify("1234567890")
    assert result.detected_type == T.USERNAME
    assert result.canonical_value == "1234567890"
    assert result.needs_confirmation
    assert TargetClassifier.resolve("1234567890", T.USERNAME).canonical_value == "1234567890"
    with pytest.raises(ClassificationError):
        TargetClassifier.resolve("1234567890", T.PHONE)


@pytest.mark.parametrize("value", ["", "  ", "Jane Smith", "abc\nxyz", "a" * 2049,
    "https://", "https://user:secret@example.com", "https://example.com:99999", "a/b", "..."])
def test_malformed_input_is_not_a_username_fallback(value):
    with pytest.raises(ClassificationError):
        TargetClassifier.classify(value)


@pytest.mark.parametrize("value,kind", [("a_b.com", T.DOMAIN), ("-bad.com", T.DOMAIN),
    ("a..com", T.DOMAIN), ("person@example.com", T.USERNAME), ("example.com", T.PHONE),
    ("localhost", T.DOMAIN), ("Alice Smith", T.ORGANIZATION)])
def test_override_validates_syntax(value, kind):
    with pytest.raises(ClassificationError):
        TargetClassifier.resolve(value, kind)


def test_internal_hostname_and_idna_override():
    assert TargetClassifier.resolve("machine.internal", T.HOSTNAME).canonical_value == "machine.internal"
    assert TargetClassifier.resolve("BÜCHER.DE", T.DOMAIN).canonical_value == "xn--bcher-kva.de"


def test_cold_classifier_never_uses_dns_or_http(monkeypatch):
    import socket
    import requests
    import tldextract
    import spider.models.classifier as module

    def denied(*args, **kwargs):
        pytest.fail("Classification attempted network access")
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(requests.Session, "send", denied)
    monkeypatch.setattr(module, "_SUFFIXES", tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None))
    assert TargetClassifier.resolve("ms.orianawren").detected_type == T.USERNAME
    assert TargetClassifier.classify("corp.co.uk").detected_type == T.DOMAIN
