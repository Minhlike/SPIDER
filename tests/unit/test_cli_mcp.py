import pytest
from typer.testing import CliRunner
from spider.cli.main import app, infer_observable_type
from spider.models.enums import ObservableType
from spider.mcp.server import create_mcp_server

runner = CliRunner()

def test_infer_observable_type():
    assert infer_observable_type("example.com") == ObservableType.DOMAIN
    assert infer_observable_type("192.168.1.1") == ObservableType.IP_ADDRESS
    assert infer_observable_type("AS15133") == ObservableType.ASN
    assert infer_observable_type("10.0.0.0/24") == ObservableType.CIDR
    assert infer_observable_type("admin@example.com") == ObservableType.EMAIL
    assert infer_observable_type("johndoe1998") == ObservableType.USERNAME

def test_cli_doctor_json():
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    assert "providers" in result.stdout
    assert "database_connected" in result.stdout

def test_cli_provider_list_json():
    result = runner.invoke(app, ["provider", "list", "--json"])
    assert result.exit_code == 0
    assert "subfinder" in result.stdout
    assert "metabigor" in result.stdout
    assert "spiderfoot" in result.stdout
    assert "maigret" in result.stdout
    assert "uncover" in result.stdout

@pytest.mark.asyncio
async def test_mcp_server_collect_and_explain(tmp_path):
    server = create_mcp_server()
    res = await server.handle_tool_call("collect", {
        "target": "example.com",
        "authorized_scope": True
    })
    assert res["status"] == "COMPLETED"
    assert "case_id" in res
    assert len(res["entities"]) > 0

    if res["assertions"]:
        asrt_id = res["assertions"][0]["id"]
        exp_res = await server.handle_tool_call("explain_assertion", {
            "assertion_id": asrt_id
        })
        assert "evidence" in exp_res
