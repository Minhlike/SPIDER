import pytest
from fastapi.testclient import TestClient
from spider.web.app import create_app

@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c

def test_api_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "HEALTHY"
    assert "providers" in data

def test_api_providers_list(client):
    res = client.get("/api/providers")
    assert res.status_code == 200
    providers = res.json()
    assert len(providers) >= 5
    ids = {p["provider_id"] for p in providers}
    assert "subfinder" in ids
    assert "metabigor" in ids
    assert "spiderfoot" in ids
    assert "maigret" in ids
    assert "uncover" in ids

def test_api_case_lifecycle(client):
    # 1. Create Case
    create_res = client.post("/api/cases", json={
        "name": "Web Test Case",
        "description": "Testing REST API",
        "tags": ["test", "web"]
    })
    assert create_res.status_code == 200
    case_data = create_res.json()
    case_id = case_data["id"]

    # 2. List Cases
    list_res = client.get("/api/cases")
    assert list_res.status_code == 200
    assert any(c["id"] == case_id for c in list_res.json())

    # 3. Get Case Details
    get_res = client.get(f"/api/cases/{case_id}")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Web Test Case"

    # 4. Export Case
    export_res = client.get(f"/api/cases/{case_id}/export")
    assert export_res.status_code == 200
    assert "summary" in export_res.json()

    # 5. Delete Case
    del_res = client.delete(f"/api/cases/{case_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "DELETED"
