import pytest
from fastapi.testclient import TestClient
from spider.web.app import create_app

@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c

def test_security_headers_and_csp(client):
    res = client.get("/")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in res.headers
    assert "default-src 'self'" in res.headers["Content-Security-Policy"]

def test_xss_payload_handling(client):
    # Test malicious XSS in case name
    xss_name = "<script>alert(1)</script>"
    res = client.post("/api/cases", json={"name": xss_name})
    assert res.status_code == 200
    case_data = res.json()
    assert case_data["name"] == xss_name

    # Clean up
    client.delete(f"/api/cases/{case_data['id']}")

def test_path_traversal_artifact_security(client):
    res = client.get("/api/explain/artifact/..%2F..%2F..%2FWindows%2Fwin.ini")
    assert res.status_code in (404, 422)
