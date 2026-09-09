import pytest
from fastapi.testclient import TestClient
from spider.web.app import create_app

@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c

def test_api_classify_endpoint(client):
    # EMAIL
    res = client.get("/api/classify?target=admin@example.com")
    assert res.status_code == 200
    assert res.json()["type"] == "EMAIL"

    # DOMAIN
    res = client.get("/api/classify?target=example.com")
    assert res.status_code == 200
    assert res.json()["type"] == "DOMAIN"

    # IP
    res = client.get("/api/classify?target=1.1.1.1")
    assert res.status_code == 200
    assert res.json()["type"] == "IP_ADDRESS"

    # PHONE
    res = client.get("/api/classify?target=%2B84901234567")
    assert res.status_code == 200
    assert res.json()["type"] == "PHONE"

    # USERNAME
    res = client.get("/api/classify?target=john_doe99")
    assert res.status_code == 200
    assert res.json()["type"] == "USERNAME"
    username_plan = res.json()["source_preflight"]
    assert username_plan["investigation_mode"] == "PERSONAL_FOOTPRINT"
    assert {s["provider_id"] for s in username_plan["sources"]} == {"github_public", "maigret"}
    assert not username_plan["internet_api_keys_applicable"]

    browser_res = client.post("/api/classify", json={"target": "john_doe99", "browser_assisted": True})
    assert browser_res.status_code == 200
    browser_sources = {s["provider_id"] for s in browser_res.json()["source_preflight"]["sources"]}
    assert {"github_public", "maigret", "coccoc_browser"} <= browser_sources

    res = client.post("/api/classify", json={"target": "example.com", "target_type": "DOMAIN"})
    assert res.status_code == 200
    domain_plan = res.json()["source_preflight"]
    assert domain_plan["investigation_mode"] == "INFRASTRUCTURE"
    assert "uncover" in {s["provider_id"] for s in domain_plan["sources"]}
    assert domain_plan["internet_api_keys_applicable"]

def test_api_settings_endpoints(client):
    # GET settings
    get_res = client.get("/api/settings")
    assert get_res.status_code == 200
    data = get_res.json()
    assert "language" in data
    assert "theme" in data
    assert "default_policy_profile" in data

    # POST settings
    post_res = client.post("/api/settings", json={
        "language": "en",
        "theme": "dark",
        "default_policy_profile": "passive_standard",
        "max_depth": 2,
        "timeout_seconds": 90,
        "api_keys": {"SHODAN": "test_shodan_key_123"}
    })
    assert post_res.status_code == 200
    assert post_res.json()["status"] == "SAVED"

    # Verify updated settings
    get_res2 = client.get("/api/settings")
    assert get_res2.status_code == 200
    data2 = get_res2.json()
    assert data2["language"] == "en"
    assert data2["theme"] == "dark"
    # Ensure secret is masked in GET
    assert data2["api_keys"]["SHODAN"] == "********"

def test_api_provider_live_test(client):
    res = client.post("/api/providers/native_dns/test")
    assert res.status_code == 200
    data = res.json()
    assert data["provider_id"] == "native_dns"
    assert data["state"] == "READY"

def test_api_case_insights_flow(client):
    # Create case
    case_res = client.post("/api/cases", json={"name": "Insights Test Case"})
    assert case_res.status_code == 200
    case_id = case_res.json()["id"]

    # Request insights
    insights_res = client.get(f"/api/cases/{case_id}/insights")
    assert insights_res.status_code == 200
    insights = insights_res.json()
    assert insights["case_id"] == case_id
    assert "entities_count" in insights
    assert "assertions_count" in insights
    assert "observations_count" in insights
    assert "provider_contributions" in insights

    # Delete case
    del_res = client.delete(f"/api/cases/{case_id}")
    assert del_res.status_code == 200
