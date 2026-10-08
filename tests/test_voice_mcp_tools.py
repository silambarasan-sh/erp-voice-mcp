"""Tests for the 5 core Alexa+ ERP voice tools registered on the MCP server."""

import pytest
from mcp_server.server import (
    get_pending_invoices,
    get_overdue_invoices,
    get_low_stock_items,
    get_pending_leaves,
    get_sales_summary,
)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_pending_invoices_tool_without_month():
    """Verify get_pending_invoices returns total count, amount, top 3 customers, and speech."""
    res = await get_pending_invoices()
    assert "speech" in res
    assert "data" in res

    data = res["data"]
    assert data["count"] > 0
    assert data["total_amount"] > 0
    assert "top_3_customers" in data
    assert len(data["top_3_customers"]) <= 3

    # Check that speech is short and contains key voice indicators
    speech = res["speech"]
    assert "pending invoices" in speech.lower()
    assert "rupees" in speech.lower()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_pending_invoices_tool_with_month():
    """Verify get_pending_invoices filters by month name or number."""
    # Test with month name
    res_oct = await get_pending_invoices(month="October")
    assert "speech" in res_oct
    assert "October" in res_oct["speech"] or "pending" in res_oct["speech"]

    # Test with numeric month string
    res_num = await get_pending_invoices(month="10")
    assert "speech" in res_num
    assert res_num["data"]["month_filter"] == "10"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_overdue_invoices_tool():
    """Verify get_overdue_invoices returns overdue invoices with customer and days overdue."""
    res = await get_overdue_invoices()
    assert "speech" in res
    assert "data" in res

    data = res["data"]
    assert data["count"] > 0
    assert len(data["invoices"]) == data["count"]

    first_inv = data["invoices"][0]
    assert "customer" in first_inv
    assert "days_overdue" in first_inv
    assert first_inv["days_overdue"] >= 0

    speech = res["speech"]
    assert "overdue" in speech.lower()
    assert "rupees" in speech.lower()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_low_stock_items_tool():
    """Verify get_low_stock_items identifies items below reorder level with supplier info."""
    res = await get_low_stock_items()
    assert "speech" in res
    assert "data" in res

    data = res["data"]
    assert data["count"] >= 5
    for item in data["items"]:
        assert item["stock_qty"] <= item["reorder_level"]
        assert "supplier" in item
        assert "lead_time_days" in item

    speech = res["speech"]
    assert "below reorder level" in speech.lower()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_pending_leaves_tool():
    """Verify get_pending_leaves returns pending requests with employee names and dates."""
    res = await get_pending_leaves()
    assert "speech" in res
    assert "data" in res

    data = res["data"]
    assert data["count"] == 8
    assert len(data["pending_leaves"]) == 8

    first_req = data["pending_leaves"][0]
    assert "employee" in first_req
    assert "department" in first_req
    assert "from_date" in first_req
    assert "to_date" in first_req

    speech = res["speech"]
    assert "8 pending leave requests" in speech or "pending leave requests" in speech


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_sales_summary_tool_periods():
    """Verify get_sales_summary for today, week, and month periods."""
    for period in ["today", "week", "month"]:
        res = await get_sales_summary(period=period)
        assert "speech" in res
        assert "data" in res

        data = res["data"]
        assert data["period"] == period
        assert "total_invoiced_amount" in data
        assert "paid_amount" in data
        assert "total_invoices_count" in data
        assert "paid_invoices_count" in data

        speech = res["speech"]
        assert "sales summary" in speech.lower()
        assert "rupees" in speech.lower()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_purchase_order_status_tool():
    """Verify get_purchase_order_status returns counts of draft vs confirmed orders and recent orders."""
    from mcp_server.server import get_purchase_order_status

    res = await get_purchase_order_status()
    assert "speech" in res
    assert "data" in res

    data = res["data"]
    assert "total_count" in data
    assert "draft_count" in data
    assert "confirmed_count" in data
    assert "recent_orders" in data
    assert data["total_count"] == data["draft_count"] + data["confirmed_count"]
    assert "purchase orders" in res["speech"].lower()

