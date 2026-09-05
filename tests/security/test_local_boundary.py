import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from spider.web.app import create_app


@pytest.fixture
def client(monkeypatch):
    from spider.web import security
    monkeypatch.setattr(security, "ALLOWED_HOSTS", {"localhost", "127.0.0.1", "::1"})
    return TestClient(create_app(), base_url="http://127.0.0.1:8765")


@pytest.mark.parametrize("path,method", [("/", "GET"), ("/api/cases", "GET"),
    ("/api/investigate", "POST"), ("/api/cases/fixture", "DELETE"),
    ("/api/providers/native_dns/test", "POST"), ("/api/settings", "POST"),
    ("/api/system/shutdown", "POST")])
@pytest.mark.parametrize("headers", [{"host": "attacker.test:8765"},
    {"host": "127.0.0.1.attacker.test"}, {"host": "attacker.test@127.0.0.1:8765"},
    {"origin": "https://attacker.test"}, {"origin": "null"},
    {"origin": "http://127.0.0.1:8766"}, {"sec-fetch-site": "cross-site"},
    {"sec-fetch-site": "same-site"}])
def test_hostile_http_rejected_before_handler(client, path, method, headers):
    response = client.request(method, path, headers=headers)
    assert response.status_code == 403
    assert "attacker" not in response.text


def test_local_browser_and_cli_allowed(client):
    assert client.get("/").status_code == 200
    assert client.post("/api/classify", json={"target": "fixture-user"},
        headers={"origin": "http://127.0.0.1:8765", "sec-fetch-site": "same-origin"}).status_code == 200
    assert client.get("/", headers=[("host", "localhost"), ("host", "127.0.0.1")]).status_code == 403


@pytest.mark.parametrize("headers", [{}, {"origin": "https://attacker.test"},
    {"origin": "http://127.0.0.1:8765", "host": "attacker.test"}])
def test_hostile_websocket_rejected(client, headers):
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect("ws://127.0.0.1:8765/ws", headers=headers):
            pytest.fail("Hostile websocket accepted")
    assert error.value.code == 1008


def test_same_origin_websocket_allowed(client):
    with client.websocket_connect("ws://127.0.0.1:8765/ws", headers={"origin": "http://127.0.0.1:8765"}) as websocket:
        websocket.send_text("ping")


def test_shutdown_refuses_unmanaged_process(client):
    response = client.post("/api/system/shutdown", headers={
        "origin": "http://127.0.0.1:8765", "sec-fetch-site": "same-origin"})
    assert response.status_code == 409


def test_shutdown_signals_only_verified_launcher_process(client, monkeypatch):
    import os
    from spider import launcher
    from spider.web import app as web_app
    state = {"pid": os.getpid(), "created": 1, "image": "fixture"}
    signalled = []
    monkeypatch.setattr(launcher, "read_state", lambda: state)
    monkeypatch.setattr(web_app.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(launcher, "signal_stop", lambda value: signalled.append(value))
    response = client.post("/api/system/shutdown", headers={
        "origin": "http://127.0.0.1:8765", "sec-fetch-site": "same-origin"})
    assert response.status_code == 202
    assert response.json()["status"] == "SHUTDOWN_REQUESTED"
    assert signalled == [state]
