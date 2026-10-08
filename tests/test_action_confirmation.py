"""Tests for action tools with confirmation steps, session state, and follow-ups."""

import pytest
from erp_core.models import PurchaseOrder, LeaveRequest, Employee
from erp_core.services import VoiceSessionService
from mcp_server.server import (
    draft_purchase_order,
    confirm_purchase_order,
    approve_leave,
    reject_leave,
    confirm_action,
    get_top_customers,
    get_pending_invoices,
    get_sales_summary,
)


@pytest.fixture(autouse=True)
def reset_voice_sessions():
    """Ensure a clean session registry before each test."""
    VoiceSessionService.reset()
    yield
    VoiceSessionService.reset()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_draft_purchase_order_creates_draft_only():
    """Verify draft_purchase_order creates DRAFT POs and never confirms without explicit confirmation."""
    session_id = "test_draft_only_session"
    res = await draft_purchase_order(session_id=session_id)

    assert "speech" in res
    assert "data" in res
    data = res["data"]

    assert data["status"] == "draft"
    assert data["requires_confirmation"] is True
    assert "draft_id" in data
    assert data["draft_id"].startswith("DRAFT-PO-")
    assert data["po_count"] >= 1
    assert len(data["po_ids"]) == data["po_count"]

    # Verify speech asks for confirmation
    assert "confirm" in res["speech"].lower()

    # Verify DB: all created POs MUST remain in draft status
    for po_id in data["po_ids"]:
        po = await PurchaseOrder.objects.aget(id=po_id)
        assert po.status == "draft"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_draft_then_confirm_purchase_order_flow():
    """Verify complete flow: draft PO -> confirm PO with draft_id -> status changes to confirmed."""
    session_id = "test_draft_confirm_flow"
    draft_res = await draft_purchase_order(session_id=session_id)
    draft_id = draft_res["data"]["draft_id"]
    po_ids = draft_res["data"]["po_ids"]

    # Confirm using the explicit draft_id
    confirm_res = await confirm_purchase_order(draft_id=draft_id, session_id=session_id)

    assert confirm_res["data"]["success"] is True
    assert confirm_res["data"]["status"] == "confirmed"
    assert confirm_res["data"]["draft_id"] == draft_id
    assert "confirmed" in confirm_res["speech"].lower()

    # Verify DB status updated to confirmed
    for po_id in po_ids:
        po = await PurchaseOrder.objects.aget(id=po_id)
        assert po.status == "confirmed"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_confirm_it_via_session_without_explicit_draft_id():
    """Verify confirming using session state when user says 'confirm it' without specifying draft ID."""
    session_id = "test_session_implicit_confirm"
    draft_res = await draft_purchase_order(session_id=session_id)
    po_ids = draft_res["data"]["po_ids"]

    # Call confirm_purchase_order without passing draft_id
    confirm_res = await confirm_purchase_order(session_id=session_id)

    assert confirm_res["data"]["success"] is True
    assert confirm_res["data"]["status"] == "confirmed"

    for po_id in po_ids:
        po = await PurchaseOrder.objects.aget(id=po_id)
        assert po.status == "confirmed"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_confirm_without_draft_fails_politely():
    """Verify confirming without an active draft fails politely with friendly message and no errors."""
    session_id = "completely_empty_session"

    confirm_res = await confirm_purchase_order(session_id=session_id)

    assert confirm_res["data"]["success"] is False
    assert "no pending draft" in confirm_res["speech"].lower() or "create a draft" in confirm_res["speech"].lower()
    assert "error" in confirm_res["data"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_approve_leave_ask_then_confirm_pattern():
    """Verify approve_leave requires confirmation and never changes data without it."""
    session_id = "test_leave_approval_session"

    # Find an existing pending leave request
    leave = await LeaveRequest.objects.filter(status="pending").select_related("employee").afirst()
    assert leave is not None
    emp_name = leave.employee.name

    # Step 1: Initial ask (confirm=False) -> MUST NOT change database status
    ask_res = await approve_leave(employee_name=emp_name, confirm=False, session_id=session_id)

    assert ask_res["data"]["requires_confirmation"] is True
    assert "confirm" in ask_res["speech"].lower()

    # Verify database status is STILL 'pending'
    leave_check = await LeaveRequest.objects.aget(id=leave.id)
    assert leave_check.status == "pending"

    # Step 2: Confirmation via universal 'confirm_action' (simulating voice 'confirm it')
    confirm_res = await confirm_action(session_id=session_id)

    assert confirm_res["data"]["success"] is True
    assert confirm_res["data"]["status"] == "approved"
    assert "approved" in confirm_res["speech"].lower()

    # Verify database status is now 'approved'
    leave_confirmed = await LeaveRequest.objects.aget(id=leave.id)
    assert leave_confirmed.status == "approved"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_reject_leave_ask_then_confirm_pattern():
    """Verify reject_leave requires confirmation before recording rejection in database."""
    session_id = "test_leave_rejection_session"

    leave = await LeaveRequest.objects.filter(status="pending").select_related("employee").afirst()
    assert leave is not None
    emp_name = leave.employee.name

    # Step 1: Initial ask
    ask_res = await reject_leave(
        employee_name=emp_name,
        reason="Peak production sprint",
        confirm=False,
        session_id=session_id,
    )

    assert ask_res["data"]["requires_confirmation"] is True
    assert "confirm" in ask_res["speech"].lower()

    # Verify DB still pending
    leave_check = await LeaveRequest.objects.aget(id=leave.id)
    assert leave_check.status == "pending"

    # Step 2: Explicit confirm=True
    confirm_res = await reject_leave(
        employee_name=emp_name,
        confirm=True,
        session_id=session_id,
    )

    assert confirm_res["data"]["success"] is True
    assert confirm_res["data"]["status"] == "rejected"

    leave_rejected = await LeaveRequest.objects.aget(id=leave.id)
    assert leave_rejected.status == "rejected"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_context_follow_up_top_customers():
    """Verify session remembers context for 'and who are the top 3 customers for that?' follow-up."""
    session_id = "test_context_customers_session"

    # 1. Query pending invoices
    inv_res = await get_pending_invoices(month="October", session_id=session_id)
    assert inv_res["data"]["count"] > 0

    # 2. Follow-up query asking for top 3 customers for that context
    cust_res = await get_top_customers(session_id=session_id)

    assert "speech" in cust_res
    assert "data" in cust_res
    assert cust_res["data"]["context"] == "pending_invoices"
    assert len(cust_res["data"]["top_customers"]) > 0

    speech = cust_res["speech"].lower()
    assert "pending invoices" in speech
    assert "top 3 customers" in speech or "customers" in speech


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_session_state_isolation():
    """Verify that distinct session IDs maintain isolated state."""
    session_a = "session_tenant_A"
    session_b = "session_tenant_B"

    # Session A drafts a purchase order
    draft_a = await draft_purchase_order(session_id=session_a)
    assert draft_a["data"]["status"] == "draft"

    # Session B has no draft -> confirm should fail politely
    confirm_b = await confirm_purchase_order(session_id=session_b)
    assert confirm_b["data"]["success"] is False

    # Session A confirms its own draft -> succeeds
    confirm_a = await confirm_purchase_order(session_id=session_a)
    assert confirm_a["data"]["success"] is True
