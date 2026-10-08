"""Tests for Alexa+ executive voice briefing and MCP tool functions."""

import pytest
from erp_core.services import VoiceBriefingService
from mcp_server.server import (
    voice_daily_erp_briefing,
    get_unpaid_invoices,
    check_inventory_stock,
    get_low_stock_items,
    list_purchase_orders,
    list_pending_leave_requests,
    get_employee_leave_summary,
)


@pytest.mark.django_db
def test_voice_daily_erp_briefing_service():
    """Verify daily executive voice briefing compiles Indian ERP state."""
    briefing = VoiceBriefingService.get_daily_briefing()
    assert briefing["unpaid_invoices_count"] > 0
    assert briefing["unpaid_invoices_total"] > 0
    assert briefing["low_stock_count"] >= 5
    assert briefing["pending_leave_requests_count"] == 8
    assert "Namaste!" in briefing["voice_summary"]
    assert "briefing" in briefing["voice_summary"].lower()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_async_mcp_voice_briefing_tool():
    """Verify calling the async voice_daily_erp_briefing MCP tool."""
    res = await voice_daily_erp_briefing()
    assert "voice_summary" in res
    assert res["unpaid_invoices_count"] >= 1
    assert res["pending_leave_requests_count"] == 8


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_async_mcp_domain_tools():
    """Verify asynchronous MCP tool invocations for all ERP domains."""
    inv_res = await get_unpaid_invoices()
    assert inv_res["count"] > 0

    stock_res = await check_inventory_stock(query="Busbar")
    assert stock_res["count"] == 1

    alerts_res = await get_low_stock_items()
    assert alerts_res["data"]["count"] >= 5

    po_res = await list_purchase_orders(status="draft")
    assert po_res["count"] >= 1

    leave_res = await list_pending_leave_requests()
    assert leave_res["count"] == 8

    emp_res = await get_employee_leave_summary(employee_query="Aarav Sharma")
    assert emp_res["success"] is True
    assert emp_res["employee"]["name"] == "Aarav Sharma"
