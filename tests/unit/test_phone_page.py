from spider.providers.browser.coccoc import phone_literal_match
from spider.providers.browser.phone_page import extract_phone_page_evidence


PHONE = "+84901234567"


def extract(html, visible, url="https://example.vn/contact", source="Tinhte"):
    return extract_phone_page_evidence(
        html, visible, PHONE, url, source, phone_literal_match)


def test_visible_social_phone_creates_public_account_candidate_without_owner_claim():
    result = extract(
        '<meta property="og:title" content="Cửa hàng Hoa Mai">',
        "Liên hệ 0901 234 567",
        "https://www.facebook.com/hoamai", "Facebook")

    assert result["candidate_account"] == "hoamai@facebook"
    assert result["candidate_name"] == "Cửa hàng Hoa Mai"
    assert result["evidence_class"] == "PUBLIC_SELF_PUBLISHED"
    assert result["literal_basis"] == "VISIBLE_PAGE_TEXT"
    assert result["identity_verified"] is False
    assert "owner" not in result and "subscriber" not in result


def test_matching_business_jsonld_extracts_organization_location_and_source_date():
    html = '''<script type="application/ld+json">{
      "@type":"LocalBusiness", "name":"Công ty Hoa Sen",
      "telephone":"+84 901 234 567", "dateModified":"2026-08-10",
      "address":{"streetAddress":"12 Nguyễn Huệ", "addressLocality":"Đà Nẵng"}
    }</script>'''
    result = extract(html, "Trang liên hệ doanh nghiệp")

    assert result["candidate_organization"] == "Công ty Hoa Sen"
    assert result["candidate_location_text"] == "12 Nguyễn Huệ, Đà Nẵng"
    assert result["evidence_class"] == "BUSINESS_CONTACT"
    assert result["literal_basis"] == "JSONLD_TELEPHONE"
    assert result["source_date"] == "2026-08-10"


def test_unrelated_page_metadata_cannot_create_phone_candidate():
    html = '''<script type="application/ld+json">{
      "@type":"Organization", "name":"Unrelated", "telephone":"0901234568"
    }</script>'''
    assert extract(html, "Không có số điện thoại cần tìm") == {}


def test_directory_page_is_labeled_directory_entry_when_no_structured_business():
    result = extract("<title>Danh bạ công khai</title>", "Hotline: 0901.234.567",
                     "https://trangvangvietnam.com/listing/hoa", "Trang Vàng Việt Nam")
    assert result["evidence_class"] == "DIRECTORY_ENTRY"
    assert result["candidate_url"] == "https://trangvangvietnam.com/listing/hoa"


def test_article_phone_is_only_a_third_party_mention():
    result = extract("<title>Bài thảo luận</title>", "Người đăng ghi 0901234567",
                     "https://voz.vn/t/topic/1", "VOZ")
    assert result["evidence_class"] == "THIRD_PARTY_MENTION"
    assert "candidate_name" not in result
