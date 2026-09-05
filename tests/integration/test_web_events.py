import pytest
from fastapi.testclient import TestClient
from spider.web.app import create_app

def test_websocket_connection():
    client = TestClient(create_app())
    with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as websocket:
        # Send a ping message
        websocket.send_text("ping")
        # Connection established cleanly
        assert websocket is not None
