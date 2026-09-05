import pytest

from spider.providers.maigret.worker import classify_priority_social_response


@pytest.mark.parametrize("site,body,status,expected", [
    ("Instagram", "<title>Login • Instagram</title>", 200, "LOGIN_REQUIRED"),
    ("Instagram", 'window._sharedData={"routePath":"\\/"}', 200, "LOGIN_REQUIRED"),
    ("Instagram", "Please wait a few minutes before you try again.", 200, "RATE_LIMITED"),
    ("Threads", '<title>Threads • Log in</title>', 200, "LOGIN_REQUIRED"),
    ("Threads", '<meta content="https://www.threads.com/login">', 200, "LOGIN_REQUIRED"),
    ("TikTok", '<div id="tiktok-verify-page">captcha</div>', 200, "BLOCKED"),
    ("TikTok", "Too many requests", 429, "RATE_LIMITED"),
    ("Instagram", "generic shell with no audited marker", 200, "PARSER_DRIFT"),
])
def test_ambiguous_social_page_is_never_treated_as_absence(site, body, status, expected):
    assert classify_priority_social_response(site, (body, status, None)) == expected


@pytest.mark.parametrize("site,body,status", [
    ("Instagram", '{"biography":"fixture"}', 200),
    ("Instagram", "Sorry, this page isn&#39;t available.", 200),
    ("Threads", '<meta property="og:type" content="profile">', 200),
    ("TikTok", '{"nickname":"Fixture"}', 200),
    ("TikTok", '{"serverCode":404}', 200),
    ("Threads", "", 404),
])
def test_audited_presence_or_absence_is_left_to_version_pinned_maigret(site, body, status):
    assert classify_priority_social_response(site, (body, status, None)) is None


def test_other_sites_and_transport_errors_are_not_reclassified():
    assert classify_priority_social_response("Other", ("generic", 200, None)) is None
    assert classify_priority_social_response("Instagram", ("generic", 0, RuntimeError())) is None
