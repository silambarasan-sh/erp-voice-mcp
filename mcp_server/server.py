"""MCP Server implementing voice-optimized tools for the ERP Voice Agent.

Exposes tools for Alexa+ to interact with the sample ERP:
1. get_pending_invoices(month: optional) -> count + total amount + top 3 customers
2. get_overdue_invoices() -> list with customer and days overdue
3. get_low_stock_items() -> items below reorder level
4. get_pending_leaves() -> employees and dates
5. get_sales_summary(period: today|week|month)

All responses return a short speech-friendly string for Alexa plus a structured data field.
Implements MCP spec version 2025-11-25 over Streamable HTTP.
"""

import os
from typing import Any, Dict, List, Optional
import django
from asgiref.sync import sync_to_async
from mcp.server.mcpserver import MCPServer

# Initialize Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "erp_core.settings")
django.setup()

from erp_core.services import (
    VoiceERPToolsService,
    InvoiceService,
    InventoryService,
    PurchaseOrderService,
    HRLeaveService,
    VoiceBriefingService,
)

SERVER_NAME = os.getenv("MCP_SERVER_NAME", "erp-voice-agent")
SERVER_VERSION = os.getenv("MCP_SERVER_VERSION", "1.0.0")

# Create the MCP Server instance
mcp_server = MCPServer(SERVER_NAME)


# ============================================================================
# Core Alexa+ Voice Tools & Context Follow-Ups
# ============================================================================

@mcp_server.tool()
async def get_pending_invoices(
    month: Optional[str] = None,
    session_id: str = "default",
) -> Dict[str, Any]:
    """Retrieve pending customer invoices with total count, total amount in rupees, and top 3 customers.

    Alexa reads the short speech summary aloud. Optionally filter by month name (e.g. 'October', 'November') or number (e.g. '10', '2026-10').
    Remembers top customers and amounts in conversational session state.

    Args:
        month: Optional month filter (e.g. 'October', '10', or '2026-10'). If omitted, returns all pending invoices.
        session_id: Conversational session identifier for contextual follow-up questions.
    """
    return await sync_to_async(VoiceERPToolsService.get_pending_invoices)(
        month=month,
        session_id=session_id,
    )


@mcp_server.tool()
async def get_overdue_invoices(session_id: str = "default") -> Dict[str, Any]:
    """Retrieve all overdue customer invoices with customer names, amounts, and number of days overdue.

    Alexa reads the short speech summary aloud. Returns a list sorted by days overdue.
    Remembers customers in conversational session state.

    Args:
        session_id: Conversational session identifier for contextual follow-up questions.
    """
    return await sync_to_async(VoiceERPToolsService.get_overdue_invoices)(
        session_id=session_id,
    )


@mcp_server.tool()
async def get_low_stock_items() -> Dict[str, Any]:
    """Retrieve all inventory items currently at or below their reorder level that require supplier replenishment.

    Alexa reads the short speech summary aloud. Returns SKU, item name, current stock, reorder level, and supplier lead time.
    """
    return await sync_to_async(VoiceERPToolsService.get_low_stock_items)()


@mcp_server.tool()
async def get_pending_leaves() -> Dict[str, Any]:
    """Retrieve all employee leave requests currently pending manager review, including employee names, departments, and dates.

    Alexa reads the short speech summary aloud. Returns employee details, leave duration, and reasons.
    """
    return await sync_to_async(VoiceERPToolsService.get_pending_leaves)()


@mcp_server.tool()
async def get_sales_summary(
    period: str = "month",
    session_id: str = "default",
) -> Dict[str, Any]:
    """Retrieve sales and invoice revenue summaries for today, this week, or this month.

    Alexa reads the short speech summary aloud. Remembers period and top customers in conversational session state.

    Args:
        period: Time window to summarize. Allowed values: 'today', 'week', or 'month'. Defaults to 'month'.
        session_id: Conversational session identifier for contextual follow-up questions.
    """
    return await sync_to_async(VoiceERPToolsService.get_sales_summary)(
        period=period,
        session_id=session_id,
    )


@mcp_server.tool()
async def get_top_customers(session_id: str = "default") -> Dict[str, Any]:
    """Follow-up tool when the user asks 'and who are the top 3 customers for that?'.

    Retrieves top customers from the current conversational session context (such as pending invoices, sales summary, or overdue invoices).

    Args:
        session_id: Conversational session identifier matching the previous query.
    """
    return await sync_to_async(VoiceERPToolsService.get_top_customers)(
        session_id=session_id,
    )


@mcp_server.tool()
async def get_purchase_order_status(session_id: str = "default") -> Dict[str, Any]:
    """Retrieve purchase order status breakdown including counts of draft vs confirmed orders and latest recent orders.

    Alexa reads the short speech summary aloud.

    Args:
        session_id: Conversational session identifier.
    """
    return await sync_to_async(VoiceERPToolsService.get_purchase_order_status)(
        session_id=session_id,
    )


# ============================================================================
# Action Tools with Ask-Then-Confirm Pattern
# ============================================================================

@mcp_server.tool()
async def draft_purchase_order(
    item_skus: Optional[List[str]] = None,
    session_id: str = "default",
) -> Dict[str, Any]:
    """Draft purchase orders for low-stock inventory items grouped by supplier without confirming.

    Auto-picks all items currently below their reorder level if no SKUs are specified.
    Creates draft orders, returns a spoken summary with a draft_id, and requires confirmation before changing status.

    Args:
        item_skus: Optional list of item SKUs to order (e.g. ['SKU-IND-001', 'SKU-IND-005']). If omitted, auto-picks all low-stock items.
        session_id: Conversational session identifier for tracking the active draft.
    """
    return await sync_to_async(VoiceERPToolsService.draft_purchase_order)(
        item_skus=item_skus,
        session_id=session_id,
    )


@mcp_server.tool()
async def confirm_purchase_order(
    draft_id: Optional[str] = None,
    session_id: str = "default",
) -> Dict[str, Any]:
    """Confirm a draft purchase order so its status becomes confirmed.

    Only alters database status to confirmed upon execution of this tool.
    If draft_id is omitted, looks up the last draft created in the session. Fails politely if no draft exists.

    Args:
        draft_id: Optional draft ID returned by draft_purchase_order (e.g. 'DRAFT-PO-10'). If omitted, uses the session's active draft.
        session_id: Conversational session identifier.
    """
    return await sync_to_async(VoiceERPToolsService.confirm_purchase_order)(
        draft_id=draft_id,
        session_id=session_id,
    )


@mcp_server.tool()
async def approve_leave(
    employee_name: str,
    confirm: bool = False,
    session_id: str = "default",
) -> Dict[str, Any]:
    """Approve an employee leave request using an ask-then-confirm workflow.

    When confirm=False (initial ask), checks the pending request and asks the user to confirm without altering status.
    When confirm=True (or when confirmed via session), changes the status to approved in the database.

    Args:
        employee_name: Full or partial employee name (e.g. 'Rajesh Sharma').
        confirm: True to execute the approval in the database; False to stage and ask for user confirmation first.
        session_id: Conversational session identifier.
    """
    return await sync_to_async(VoiceERPToolsService.approve_leave)(
        employee_name=employee_name,
        confirm=confirm,
        session_id=session_id,
    )


@mcp_server.tool()
async def reject_leave(
    employee_name: str,
    reason: str = "",
    confirm: bool = False,
    session_id: str = "default",
) -> Dict[str, Any]:
    """Reject an employee leave request using an ask-then-confirm workflow.

    When confirm=False (initial ask), asks the user to confirm without altering status.
    When confirm=True (or when confirmed via session), changes the status to rejected and records the rejection reason.

    Args:
        employee_name: Full or partial employee name (e.g. 'Rajesh Sharma').
        reason: Reason for rejection (e.g. 'Peak project milestone').
        confirm: True to execute the rejection in the database; False to stage and ask for user confirmation first.
        session_id: Conversational session identifier.
    """
    return await sync_to_async(VoiceERPToolsService.reject_leave)(
        employee_name=employee_name,
        reason=reason,
        confirm=confirm,
        session_id=session_id,
    )


@mcp_server.tool()
async def confirm_action(session_id: str = "default") -> Dict[str, Any]:
    """Universal confirmation handler when the user simply says 'confirm it'.

    Executes whichever action (purchase order draft, leave approval, leave rejection) is pending confirmation in the session.

    Args:
        session_id: Conversational session identifier.
    """
    return await sync_to_async(VoiceERPToolsService.confirm_action)(
        session_id=session_id,
    )


# ============================================================================
# AWS Builder Layer: Amazon Bedrock & Strands ERP Planner Agent
# ============================================================================

@mcp_server.tool()
async def plan_erp_replenishment(
    prompt: str,
    session_id: str = "default",
) -> Dict[str, Any]:
    """Use Amazon Bedrock and Strands Agents SDK to plan multi-step ERP replenishment.

    Processes natural language instructions such as 'Restock everything that's running low from the fastest supplier'.
    Analyzes warehouse inventory, evaluates supplier lead times, drafts purchase orders in SQLite, and stages them for confirmation.

    Args:
        prompt: Natural language instruction (e.g. 'Restock everything running low from the fastest supplier').
        session_id: Conversational session identifier for confirmation state.
    """
    from aws_planner.agent import ERPPlannerAgent

    return await sync_to_async(ERPPlannerAgent.plan_and_execute)(
        prompt=prompt,
        session_id=session_id,
    )


# ============================================================================
# Additional Domain & Executive Voice Tools
# ============================================================================

@mcp_server.tool()
async def voice_daily_erp_briefing() -> Dict[str, Any]:
    """Provide a 30-second executive voice briefing across all ERP domains.

    Ideal for Alexa+ morning briefings: returns spoken summary and metrics
    covering unpaid invoices, low inventory, draft purchase orders, and leave requests.
    """
    return await sync_to_async(VoiceBriefingService.get_daily_briefing)()


@mcp_server.tool()
async def get_unpaid_invoices(customer_name: Optional[str] = None) -> Dict[str, Any]:
    """Query unpaid (pending or overdue) invoices with a voice-friendly spoken summary.

    Args:
        customer_name: Optional customer name filter (e.g. 'Infosys' or 'Tata').
    """
    return await sync_to_async(InvoiceService.get_unpaid_invoices)(customer_name=customer_name)


@mcp_server.tool()
async def get_invoice(invoice_no: str) -> Dict[str, Any]:
    """Retrieve details and status for a specific invoice.

    Args:
        invoice_no: The unique invoice identifier (e.g. 'INV-2026-101').
    """
    return await sync_to_async(InvoiceService.get_invoice_details)(invoice_no=invoice_no)


@mcp_server.tool()
async def create_invoice(
    customer_name: str,
    amount: float,
    due_date: str,
    invoice_no: Optional[str] = None,
    city: str = "Mumbai",
) -> Dict[str, Any]:
    """Create a new customer invoice in the ERP system.

    Args:
        customer_name: Name of customer company.
        amount: Invoice total amount in INR (e.g. 50000.00).
        due_date: Due date formatted as YYYY-MM-DD.
        invoice_no: Optional custom invoice number.
        city: City where customer is located.
    """
    return await sync_to_async(InvoiceService.create_invoice)(
        customer_name=customer_name,
        amount=amount,
        due_date_str=due_date,
        invoice_no=invoice_no,
        city=city,
    )


@mcp_server.tool()
async def pay_invoice(invoice_no: str) -> Dict[str, Any]:
    """Mark a customer invoice as paid.

    Args:
        invoice_no: The unique invoice identifier (e.g. 'INV-2026-102').
    """
    return await sync_to_async(InvoiceService.mark_invoice_paid)(invoice_no=invoice_no)


@mcp_server.tool()
async def check_inventory_stock(query: Optional[str] = None) -> Dict[str, Any]:
    """Check warehouse stock levels by item name or SKU.

    Args:
        query: Optional search term matching item name or SKU (e.g. 'Busbar' or 'SKU-IND-001').
    """
    return await sync_to_async(InventoryService.check_stock)(query=query)


@mcp_server.tool()
async def adjust_inventory_stock(
    sku: str,
    quantity_delta: int,
) -> Dict[str, Any]:
    """Adjust the physical stock count for an inventory SKU up or down.

    Args:
        sku: Unique item SKU (e.g. 'SKU-IND-001').
        quantity_delta: Quantity to add (positive) or deduct (negative).
    """
    return await sync_to_async(InventoryService.adjust_stock)(
        sku=sku,
        quantity_delta=quantity_delta,
    )


@mcp_server.tool()
async def list_purchase_orders(status: Optional[str] = None) -> Dict[str, Any]:
    """List purchase orders filtered optionally by status ('draft' or 'confirmed').

    Args:
        status: Optional status filter: 'draft' or 'confirmed'.
    """
    return await sync_to_async(PurchaseOrderService.list_purchase_orders)(status=status)


@mcp_server.tool()
async def create_purchase_order(
    supplier_name: str,
    items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Create a new purchase order with line items.

    Args:
        supplier_name: Name of the supplier.
        items: List of item orders with SKU and qty, e.g. [{'sku': 'SKU-IND-001', 'qty': 20}].
    """
    return await sync_to_async(PurchaseOrderService.create_purchase_order)(
        supplier_name=supplier_name,
        items=items,
    )



@mcp_server.tool()
async def get_employee_leave_summary(employee_query: str) -> Dict[str, Any]:
    """Look up employee details and recent leave requests.

    Args:
        employee_query: Employee full name (e.g. 'Aarav Sharma' or 'Priya Patel').
    """
    return await sync_to_async(HRLeaveService.get_employee_leave_summary)(employee_query=employee_query)


@mcp_server.tool()
async def request_leave(
    employee_name: str,
    from_date: str,
    to_date: str,
    reason: str = "",
) -> Dict[str, Any]:
    """Submit an employee leave request.

    Args:
        employee_name: Employee name.
        from_date: Start date formatted as YYYY-MM-DD.
        to_date: End date formatted as YYYY-MM-DD.
        reason: Optional reason for time off.
    """
    return await sync_to_async(HRLeaveService.request_leave)(
        employee_name=employee_name,
        from_date_str=from_date,
        to_date_str=to_date,
        reason=reason,
    )


@mcp_server.tool()
async def list_pending_leave_requests() -> Dict[str, Any]:
    """List all pending employee leave requests awaiting manager approval."""
    return await sync_to_async(HRLeaveService.list_pending_leave_requests)()


@mcp_server.tool()
async def decide_leave_request(request_id: int, approve: bool = True) -> Dict[str, Any]:
    """Approve or reject a pending leave request.

    Args:
        request_id: The integer ID of the leave request.
        approve: True to approve, False to reject.
    """
    return await sync_to_async(HRLeaveService.decide_leave_request)(
        request_id=request_id,
        approve=approve,
    )
