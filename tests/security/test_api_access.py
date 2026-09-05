"""Synthetic credentials only; real account checks are an explicit separate script."""
import asyncio
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from spider.providers.uncover import api_access as access
from spider.providers.uncover.adapter import UncoverAdapter
from spider.storage.key_store import LocalKeyStore
from spider.web.api import settings
from spider.web.app import create_app

KEYS = {"SHODAN_API_KEY": "synthetic-shodan-sentinel-+42", "CENSYS_API_TOKEN": "synthetic-censys-sentinel-42",
        "CENSYS_ORGANIZATION_ID": "00000000-0000-0000-0000-000000000042", "FOFA_EMAIL": "fixture@example.invalid",
        "FOFA_KEY": "synthetic-fofa-sentinel-42"}


@pytest.mark.parametrize("engine", list(access.REQUIREMENTS))
def test_each_engine_requires_every_field(engine):
    required = access.REQUIREMENTS[engine]
    assert access.engine_presence(KEYS)[engine]["configured"]
    for field in required:
        incomplete = {k: v for k, v in KEYS.items() if k != field}
        adapter = UncoverAdapter(key_loader=lambda: incomplete)
        assert not adapter._has_keys(engine)
        assert field in access.engine_presence(incomplete)[engine]["missing_fields"]


def test_whole_bundle_precedence_and_no_legacy_censys_guess():
    assert not access.engine_presence(access.canonical_keys({"censys_id":"old-id", "censys_secret":"old-secret"}))["censys"]["configured"]
    resolved = access.effective_keys({"CENSYS_API_TOKEN": "new-token"}, KEYS)
    assert resolved["CENSYS_ORGANIZATION_ID"] == ""
    assert resolved["SHODAN_API_KEY"] == KEYS["SHODAN_API_KEY"]
    assert access.effective_keys({"SHODAN_API_KEY":""}, KEYS)["SHODAN_API_KEY"] == ""


def test_censys_free_and_fofa_key_only_are_complete_credentials():
    free_censys = {"CENSYS_API_TOKEN": "synthetic-free-token"}
    key_only_fofa = {"FOFA_KEY": "synthetic-fofa-key"}
    assert access.engine_presence(free_censys)["censys"] == {
        "configured": True, "missing_fields": [], "optional_fields": ["CENSYS_ORGANIZATION_ID"]
    }
    assert access.engine_presence(key_only_fofa)["fofa"] == {
        "configured": True, "missing_fields": [], "optional_fields": ["FOFA_EMAIL"]
    }


@pytest.mark.parametrize("engine", list(access.REQUIREMENTS))
def test_child_environment_is_least_privilege(engine, monkeypatch):
    for name, value in KEYS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("HTTPS_PROXY", "https://proxy.invalid")
    monkeypatch.setenv("SSL_CERT_FILE", "untrusted.pem")
    monkeypatch.setenv("UNRELATED_API_KEY", "other-key")
    before = os.environ.copy()
    env = access.child_environment(engine, KEYS)
    assert all(env.get(name) == KEYS[name] for name in access.REQUIREMENTS[engine])
    allowed_credentials = set(access.REQUIREMENTS[engine]) | set(access.OPTIONAL_FIELDS.get(engine, ()))
    assert not any(name in env for name in set(access.FIELDS) - allowed_credentials)
    assert not any(name in env for name in ("HTTPS_PROXY", "SSL_CERT_FILE", "UNRELATED_API_KEY"))
    assert dict(os.environ) == before


def test_settings_roundtrip_pairs_rotation_deletion_and_masks(caplog):
    client = TestClient(create_app())
    response = client.post("/api/settings", json={"api_keys": KEYS})
    assert response.status_code == 200
    status = response.json()["credential_status"]
    assert all(status[engine]["configured"] for engine in access.REQUIREMENTS)
    assert status["whatismyip"]["configured"] is False
    assert access.saved_keys() | KEYS == access.saved_keys()
    for path in settings.SETTINGS_FILE.parent.iterdir():
        if path.is_file():
            assert all(value.encode() not in path.read_bytes() for value in KEYS.values())
    assert "api_keys" not in json.loads(settings.SETTINGS_FILE.read_text())
    for engine, names in access.REQUIREMENTS.items():
        response = client.post("/api/settings", json={"api_keys": {name:"" for name in names}})
        assert not response.json()["credential_status"][engine]["configured"]
        assert all(access.saved_keys()[name] == "" for name in names)
    assert all(value not in response.text + caplog.text for value in KEYS.values())


@pytest.mark.asyncio
async def test_new_ui_keys_reach_adapter_from_dpapi_without_restart(monkeypatch):
    adapter = UncoverAdapter()
    assert not adapter._has_keys()
    client = TestClient(create_app())
    client.post("/api/settings", json={"api_keys": KEYS})
    assert all(adapter._has_keys(engine) for engine in access.REQUIREMENTS)
    assert not any(name in os.environ for name in KEYS)
    monkeypatch.setattr(access, "verified_runtime", lambda binary: True)
    health = await adapter.health()
    assert health.credential_state == "UNTESTED" and not health.live_verified


@pytest.mark.parametrize("engine", list(access.REQUIREMENTS))
@pytest.mark.parametrize("state", sorted(access.STATES))
def test_connection_api_states_never_echo_keys(engine, state, monkeypatch, caplog):
    calls = []
    async def check(actual, keys):
        calls.append(actual)
        assert all(keys[k] == KEYS[k] for k in access.REQUIREMENTS[engine])
        return access.result_state(actual, state, "REQUEST_ACCEPTED")
    monkeypatch.setattr(access, "run_engine", check)
    client = TestClient(create_app())
    client.post("/api/settings", json={"api_keys": KEYS})
    response = client.post(f"/api/settings/test/{engine}")
    assert response.json()["state"] == state
    assert response.headers["cache-control"] == "no-store"
    assert calls == [engine]
    assert all(value not in response.text + caplog.text for value in KEYS.values())


def test_cache_key_rotation_and_delete_invalidate_success(monkeypatch):
    calls = []
    async def check(engine, keys):
        calls.append(True)
        return access.result_state(engine, "VALID", "ACCOUNT_VERIFIED_SEARCH_NOT_TESTED")
    monkeypatch.setattr(access, "run_engine", check)
    client = TestClient(create_app())
    client.post("/api/settings", json={"api_keys": KEYS})
    assert client.post("/api/settings/test/censys").json()["state"] == "VALID"
    assert client.post("/api/settings/test/censys").json()["cached"] is True
    assert len(calls) == 1
    client.post("/api/settings", json={"api_keys":{"CENSYS_ORGANIZATION_ID":"new-synthetic-org"}})
    assert client.get("/api/settings").json()["credential_status"]["censys"]["test"] is None
    client.post("/api/settings", json={"api_keys":{"CENSYS_API_TOKEN":"", "CENSYS_ORGANIZATION_ID":""}})
    assert client.get("/api/settings").json()["credential_status"]["censys"]["test"] is None


@pytest.mark.asyncio
async def test_save_during_check_rejects_stale_success(monkeypatch):
    async def check(engine, keys):
        settings.update_settings(settings.UpdateSettingsRequest(api_keys={"SHODAN_API_KEY":"changed-synthetic"}))
        return access.result_state(engine, "VALID", "ACCOUNT_VERIFIED_SEARCH_NOT_TESTED")
    monkeypatch.setattr(access, "run_engine", check)
    settings.update_settings(settings.UpdateSettingsRequest(api_keys=KEYS))
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as caught:
        await settings.test_engine_access("shodan")
    assert caught.value.status_code == 409


def test_foreign_origin_host_and_validation_are_safe():
    client = TestClient(create_app())
    for headers in ({"host":"evil.invalid"}, {"origin":"https://evil.invalid"}, {"sec-fetch-site":"cross-site"}):
        response = client.post("/api/settings", json={"api_keys":KEYS}, headers=headers)
        assert response.status_code == 403
    response = client.post("/api/settings/test/shodan", headers={"origin":"https://evil.invalid"})
    assert response.status_code == 403
    response = client.post("/api/settings/test/not-an-engine")
    assert response.status_code == 422
    assert "input" not in response.text


@pytest.mark.asyncio
async def test_unverified_binary_never_receives_keys(monkeypatch):
    def spawn(*args, **kwargs):
        raise AssertionError("must not spawn unverified runtime")
    monkeypatch.setattr(access.asyncio, "create_subprocess_exec", spawn)
    result = await access.run_engine("shodan", KEYS, binary=Path("tools/uncover/uncover.exe"))
    assert result["reason"] == "RUNTIME_UNAVAILABLE"


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["leak", "encoded", "malformed", "timeout", "cancel", "valid"])
async def test_real_child_cleanup_redaction_and_environment(tmp_path, monkeypatch, action, caplog):
    worker = tmp_path / "worker.py"
    worker.write_text('''import json, os, sys, time
action = sys.argv[1]
value = os.environ['SHODAN_API_KEY']
assert 'FOFA_KEY' not in os.environ and 'CENSYS_API_TOKEN' not in os.environ
if action in ('timeout', 'cancel'): time.sleep(60)
elif action == 'leak': print(value)
elif action == 'encoded':
 from urllib.parse import quote
 print(quote(value, safe=''))
elif action == 'malformed': print('not json')
else: print(json.dumps({'state':'VALID', 'reason':'SEARCH_VERIFIED', 'results':[{'engine':'shodan','ip':'192.0.2.1'}],
 'request_journal':[{'sequence':1,'method':'GET','destination':'api.shodan.io','purpose':'account_validation','http_status':200,'outcome':'HTTP_200'}]}))
print(value, file=sys.stderr)
''')
    original = asyncio.create_subprocess_exec
    children = []
    async def spawn(*command, **kwargs):
        assert not any(v in str(command) for v in KEYS.values())
        process = await original(sys.executable, str(worker), action, **kwargs)
        children.append(process)
        return process
    monkeypatch.setattr(access, "verified_runtime", lambda binary: True)
    monkeypatch.setattr(access.asyncio, "create_subprocess_exec", spawn)
    task = asyncio.create_task(access.run_engine("shodan", KEYS, timeout=.15 if action == "timeout" else 3))
    if action == "cancel":
        while not children:
            await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        result = await task
        assert result["state"] == ("VALID" if action == "valid" else "NETWORK_ERROR")
        assert not access.contains_secret(json.dumps(result), KEYS)
    assert children and all(p.returncode is not None for p in children)
    assert not access.contains_secret(caplog.text, KEYS)


def test_untrusted_rows_and_raw_provider_fields_are_not_artifacts():
    rows = [{"engine":"shodan", "ip":"192.0.2.1", "raw":{"key":KEYS["SHODAN_API_KEY"]}},
            {"engine":"fofa", "ip":"192.0.2.2", "url":"https://example.invalid/path?token=not-a-real-key"},
            {"engine":"censys", "ip":"invalid", "url":"https://user:pass@example.invalid"}]
    assert access.clean_rows(rows, KEYS) == [{"engine":"fofa", "ip":"192.0.2.2", "url":"https://example.invalid/path"}]
