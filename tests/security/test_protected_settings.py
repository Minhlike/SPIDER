import json
import os

import pytest
from fastapi.testclient import TestClient

from spider.storage.key_store import KeyStoreError, LocalKeyStore, WindowsDPAPI
from spider.web.api import settings
from spider.web.app import create_app


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI gate requires Windows")
SENTINEL = "regression-only-not-a-provider-key-71a2"


def test_dpapi_roundtrip_and_tampering(tmp_path):
    vault = LocalKeyStore(tmp_path / "keys.dpapi")
    vault.save({"SHODAN": SENTINEL})
    blob = vault.path.read_bytes()
    assert SENTINEL.encode() not in blob
    assert vault.load() == {"SHODAN": SENTINEL}
    vault.path.write_bytes(blob[:-8] + b"tampered")
    with pytest.raises(KeyStoreError):
        vault.load()


def test_legacy_migration_preserves_preferences_and_removes_plaintext():
    settings.SETTINGS_FILE.write_text(json.dumps({
        "language": "en", "theme": "dark", "api_keys": {"SHODAN": SENTINEL}
    }))
    result = settings.load_settings()
    assert result["api_keys"]["SHODAN"] == SENTINEL
    public = json.loads(settings.SETTINGS_FILE.read_text())
    assert public["language"] == "en" and public["theme"] == "dark"
    assert "api_keys" not in public
    for path in settings.SETTINGS_FILE.parent.iterdir():
        if path.is_file():
            assert SENTINEL.encode() not in path.read_bytes()
    assert settings.load_settings() == result


def test_failed_migration_keeps_recoverable_legacy_file(monkeypatch, caplog):
    legacy = json.dumps({"api_keys": {"SHODAN": SENTINEL}})
    settings.SETTINGS_FILE.write_text(legacy)
    def fail(*args):
        raise RuntimeError(SENTINEL)
    monkeypatch.setattr(WindowsDPAPI, "protect", fail)
    with pytest.raises(KeyStoreError) as error:
        settings.load_settings()
    assert SENTINEL not in str(error.value)
    assert SENTINEL not in caplog.text
    assert settings.SETTINGS_FILE.read_text() == legacy
    assert not settings.SETTINGS_FILE.with_name("api-keys.dpapi").exists()


def test_api_masks_updates_preserves_mask_and_deletes(caplog):
    client = TestClient(create_app())
    assert client.get("/api/settings").json()["language"] == "vi"
    assert client.get("/api/settings").json()["theme"] == "light"
    response = client.post("/api/settings", json={"api_keys": {"SHODAN": SENTINEL}})
    assert response.status_code == 200
    assert response.json()["api_keys"]["SHODAN"] == "********"
    assert SENTINEL not in response.text
    assert SENTINEL not in client.get("/api/settings").text
    client.post("/api/settings", json={"api_keys": {"SHODAN": "********"}, "theme": "dark"})
    assert settings.load_settings()["api_keys"]["SHODAN"] == SENTINEL
    assert "api_keys" not in json.loads(settings.SETTINGS_FILE.read_text())
    client.post("/api/settings", json={"api_keys": {"SHODAN": ""}})
    assert settings.load_settings()["api_keys"]["SHODAN"] == ""
    assert SENTINEL not in caplog.text


def test_whatismyip_key_is_dpapi_only_and_masked(caplog):
    client = TestClient(create_app())
    response = client.post("/api/settings", json={
        "api_keys": {"WHATISMYIP_API_KEY": SENTINEL}})
    assert response.status_code == 200
    assert response.json()["api_keys"]["WHATISMYIP_API_KEY"] == "********"
    assert response.json()["credential_status"]["whatismyip"]["configured"] is True
    assert "api_keys" not in json.loads(settings.SETTINGS_FILE.read_text())
    assert SENTINEL.encode() not in settings.SETTINGS_FILE.with_name("api-keys.dpapi").read_bytes()
    assert SENTINEL not in response.text and SENTINEL not in caplog.text


@pytest.mark.parametrize("payload", [
    {"api_keys": {"SHODAN": {"invalid": SENTINEL}}},
    {"api_keys": {SENTINEL: "value"}},
    {"api_keys": SENTINEL},
    {"max_depth": SENTINEL},
])
def test_invalid_input_never_echoes_secret(payload, caplog):
    response = TestClient(create_app()).post("/api/settings", json=payload)
    assert response.status_code == 422
    assert SENTINEL not in response.text
    assert SENTINEL not in caplog.text


def test_corrupt_vault_fails_closed_without_overwrite(caplog):
    settings.save_settings({**settings.DEFAULT_SETTINGS, "api_keys": {"SHODAN": SENTINEL}})
    vault_path = settings.SETTINGS_FILE.with_name("api-keys.dpapi")
    vault_path.write_bytes(b"corrupt")
    client = TestClient(create_app())
    for response in (client.get("/api/settings"), client.post("/api/settings", json={"theme": "dark"})):
        assert response.status_code == 503
        assert SENTINEL not in response.text
    assert vault_path.read_bytes() == b"corrupt"
    assert SENTINEL not in caplog.text


def test_failed_write_never_reports_saved(monkeypatch, caplog):
    def fail(*args):
        raise OSError(SENTINEL)
    settings.load_settings()
    monkeypatch.setattr(WindowsDPAPI, "protect", fail)
    response = TestClient(create_app()).post("/api/settings", json={"api_keys": {"SHODAN": SENTINEL}})
    assert response.status_code == 503
    assert SENTINEL not in response.text
    assert SENTINEL not in caplog.text
