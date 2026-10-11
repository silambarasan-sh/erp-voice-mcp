"""Tests for MCP Protocol 2025-11-25 spec and Streamable HTTP transport compliance."""

import pytest
import httpx
from mcp_server.server import mcp_server
from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS, SUPPORTED_PROTOCOL_VERSIONS


def test_mcp_sdk_spec_version_support():
    """Verify that the installed MCP SDK explicitly supports spec version 2025-11-25."""
    target_spec = "2025-11-25"
    assert target_spec in SUPPORTED_PROTOCOL_VERSIONS, (
        f"Target spec {target_spec} is not in SUPPORTED_PROTOCOL_VERSIONS: {SUPPORTED_PROTOCOL_VERSIONS}"
    )
    assert target_spec in HANDSHAKE_PROTOCOL_VERSIONS, (
        f"Target spec {target_spec} is not in HANDSHAKE_PROTOCOL_VERSIONS: {HANDSHAKE_PROTOCOL_VERSIONS}"
    )


def test_registered_mcp_tools():
    """Verify that all required voice agent tools are registered with the MCP server."""
    tool_names = [tool.name for tool in mcp_server._tool_manager.list_tools()]

    expected_tools = [
        "get_pending_invoices",
        "get_overdue_invoices",
        "get_low_stock_items",
        "get_pending_leaves",
        "get_sales_summary",
        "get_top_customers",
        "get_purchase_order_status",
        "draft_purchase_order",
        "confirm_purchase_order",
        "approve_leave",
        "reject_leave",
        "confirm_action",
        "plan_erp_replenishment",
        "voice_daily_erp_briefing",
        "get_unpaid_invoices",
        "get_invoice",
        "create_invoice",
        "pay_invoice",
        "check_inventory_stock",
        "adjust_inventory_stock",
        "list_purchase_orders",
        "create_purchase_order",
        "get_employee_leave_summary",
        "request_leave",
        "list_pending_leave_requests",
        "decide_leave_request",
    ]

    for expected in expected_tools:
        assert expected in tool_names, f"Expected tool '{expected}' is missing from MCP Server."


@pytest.mark.django_db(transaction=True)
def test_health_check_endpoint(test_client):
    """Verify /health endpoint returns healthy status, 2025-11-25 spec version, and mode transparency."""
    from aws_planner.config import AWSConfig
    AWSConfig.set_last_live_call("not_called_yet")

    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["mcp_spec_version"] == "2025-11-25"
    assert data["transport"] == "streamable_http"
    assert data["database_connected"] is True
    assert data["mcp_endpoint"] == "/mcp"
    assert data["configured_mode"] == "mock"
    assert data["last_live_call"] == "not_called_yet"
    assert data["planner_mode"] == "mock"

    # Verify protocol version response header
    assert response.headers.get("mcp-protocol-version") == "2025-11-25"


@pytest.mark.django_db(transaction=True)
def test_health_check_endpoint_never_claims_bedrock_without_successful_live_call(test_client, monkeypatch):
    """Verify /health never reports planner_mode 'bedrock' unless a live call has succeeded."""
    from aws_planner.config import AWSConfig

    monkeypatch.setenv("AWS_MOCK_MODE", "false")

    # 1. Configured mode is bedrock, but no live call has occurred yet
    AWSConfig.set_last_live_call("not_called_yet")
    res1 = test_client.get("/health").json()
    assert res1["configured_mode"] == "bedrock"
    assert res1["last_live_call"] == "not_called_yet"
    assert res1["planner_mode"] != "bedrock"
    assert res1["planner_mode"] == "mock"

    # 2. Live call was attempted but failed
    AWSConfig.set_last_live_call("failed")
    res2 = test_client.get("/health").json()
    assert res2["configured_mode"] == "bedrock"
    assert res2["last_live_call"] == "failed"
    assert res2["planner_mode"] != "bedrock"
    assert res2["planner_mode"] == "fallback"

    # 3. Only when last live call succeeded can planner_mode claim 'bedrock'
    AWSConfig.set_last_live_call("ok")
    res3 = test_client.get("/health").json()
    assert res3["configured_mode"] == "bedrock"
    assert res3["last_live_call"] == "ok"
    assert res3["planner_mode"] == "bedrock"


@pytest.mark.django_db(transaction=True)
def test_root_endpoint(test_client):
    """Verify root endpoint provides discovery info for Alexa+ and MCP clients."""
    response = test_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["mcp_spec_version"] == "2025-11-25"
    assert data["streamable_http_url"] == "/mcp"
    assert response.headers.get("mcp-protocol-version") == "2025-11-25"


@pytest.mark.django_db(transaction=True)
def test_streamable_http_endpoint_protocol_version_negotiation(test_client):
    """Verify /mcp Streamable HTTP endpoint accepts MCP-Protocol-Version: 2025-11-25."""
    headers = {
        "MCP-Protocol-Version": "2025-11-25",
        "Accept": "text/event-stream, application/json",
    }
    # A request with MCP-Protocol-Version verifies protocol header negotiation
    response = test_client.get("/mcp", headers=headers)
    # The response can be 400 (missing session ID) or 200/405, but MUST NOT be 404
    assert response.status_code != 404
    assert response.headers.get("mcp-protocol-version") == "2025-11-25"

