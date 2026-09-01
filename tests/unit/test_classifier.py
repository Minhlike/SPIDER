import pytest
from spider.models.classifier import TargetClassifier
from spider.models.enums import ObservableType

def test_classifier_emails():
    assert TargetClassifier.classify("user@example.com").detected_type == ObservableType.EMAIL
    assert TargetClassifier.classify("admin@gov.vn").detected_type == ObservableType.EMAIL
    assert TargetClassifier.classify("contact@startup.io").detected_type == ObservableType.EMAIL
    assert TargetClassifier.classify("info@corp.co.uk").detected_type == ObservableType.EMAIL
    assert TargetClassifier.classify("test.user+tag@domain.net").detected_type == ObservableType.EMAIL

def test_classifier_accounts_vs_emails():
    # Account is username@platform (no TLD dot after @)
    assert TargetClassifier.classify("johndoe@github").detected_type == ObservableType.ACCOUNT
    assert TargetClassifier.classify("alice@reddit").detected_type == ObservableType.ACCOUNT

def test_classifier_ips_and_cidrs():
    assert TargetClassifier.classify("93.184.216.34").detected_type == ObservableType.IP_ADDRESS
    assert TargetClassifier.classify("2606:4700:10::6814:179a").detected_type == ObservableType.IPV6_ADDRESS
    assert TargetClassifier.classify("192.168.1.0/24").detected_type == ObservableType.CIDR
    assert TargetClassifier.classify("2001:db8::/32").detected_type == ObservableType.CIDR

def test_classifier_asns():
    res = TargetClassifier.classify("AS15133")
    assert res.detected_type == ObservableType.ASN
    assert res.canonical_value == "AS15133"
    assert TargetClassifier.classify("as45899").canonical_value == "AS45899"

def test_classifier_phones():
    assert TargetClassifier.classify("+84901234567").detected_type == ObservableType.PHONE
    assert TargetClassifier.classify("+14155552671").detected_type == ObservableType.PHONE

def test_classifier_domains_and_hostnames():
    assert TargetClassifier.classify("example.com").detected_type == ObservableType.DOMAIN
    assert TargetClassifier.classify("sub.example.com").detected_type == ObservableType.HOSTNAME
    assert TargetClassifier.classify("https://example.com/login").detected_type == ObservableType.URL
