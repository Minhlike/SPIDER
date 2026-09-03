"""Keep every settings test away from the user's settings and protected keys."""
import pytest


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    from spider.web.api import settings
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(settings, "ALLOWED_SETTINGS_HOSTS", {"testserver", "127.0.0.1", "localhost", "::1"})
    monkeypatch.setattr(settings, "CHECK_CACHE", settings.CheckCache())
    # A full test run must never consume real credentials inherited from its shell.
    from spider.providers.uncover.api_access import FIELDS
    for name in FIELDS:
        monkeypatch.delenv(name, raising=False)
