"""Keep every settings test away from the user's settings and protected keys."""
import pytest


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    from spider.web.api import settings
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
