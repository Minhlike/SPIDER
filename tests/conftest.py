"""Keep every settings test away from the user's settings and protected keys."""
import pytest


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    from spider.storage.database import DatabaseManager
    from spider.storage.repositories.artifact_repo import ArtifactRepository
    original_db, original_artifacts = DatabaseManager.__init__, ArtifactRepository.__init__
    def isolated_db(self, db_path=None):
        original_db(self, str(tmp_path / "default.db") if db_path in (None, "data/spider.db") else db_path)
    def isolated_artifacts(self, artifacts_dir=None):
        original_artifacts(self, str(tmp_path / "runs") if artifacts_dir in (None, "data/runs") else artifacts_dir)
    monkeypatch.setattr(DatabaseManager, "__init__", isolated_db)
    monkeypatch.setattr(ArtifactRepository, "__init__", isolated_artifacts)
    from spider.web import app as web_app, security
    from spider.core.factory import create_spider_service
    def isolated_service(**kwargs):
        kwargs.setdefault("db_path", str(tmp_path / "web.db"))
        kwargs.setdefault("artifacts_dir", str(tmp_path / "runs"))
        return create_spider_service(**kwargs)
    monkeypatch.setattr(web_app, "create_spider_service", isolated_service)
    monkeypatch.setattr(security, "ALLOWED_HOSTS", security.ALLOWED_HOSTS | {"testserver"})
    from spider.web.api import settings
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(settings, "ALLOWED_SETTINGS_HOSTS", {"testserver", "127.0.0.1", "localhost", "::1"})
    monkeypatch.setattr(settings, "CHECK_CACHE", settings.CheckCache())
    # A full test run must never consume real credentials inherited from its shell.
    from spider.providers.uncover.api_access import FIELDS
    for name in FIELDS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("WHATISMYIP_API_KEY", raising=False)
