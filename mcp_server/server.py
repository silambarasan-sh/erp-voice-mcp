"""MCP Server implementing tools for the ERP Voice Agent.

Exposes tools for Invoices, Inventory, Purchase Orders, and HR Leave.
Integrates with Django 5 SQLite backend using official MCP Python SDK.
Designed specifically for voice assistants like Alexa+.
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
# Executive Voice Tools
# ============================================================================

@mcp_server.tool()
async def voice_daily_erp_briefing() -> Dict[str, Any]:
    """Provide a 30-second executive voice briefing across all ERP domains.

    Ideal for Alexa+ morning briefings: returns spoken summary and metrics
    covering unpaid invoices, low inventory, draft purchase orders, and leave requests.
    """
    return await sync_to_async(VoiceBriefingService.get_daily_briefing)()


# ============================================================================
# Invoices Tools
# ============================================================================

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


# ============================================================================
# Inventory Tools
# ============================================================================

@mcp_server.tool()
async def check_inventory_stock(query: Optional[str] = None) -> Dict[str, Any]:
    """Check warehouse stock levels by item name or SKU.

    Args:
        query: Optional search term matching item name or SKU (e.g. 'Busbar' or 'SKU-IND-001').
    """
    return await sync_to_async(InventoryService.check_stock)(query=query)


@mcp_server.tool()
async def get_low_stock_alerts() -> Dict[str, Any]:
    """Get all inventory items currently at or below their reorder level."""
    return await sync_to_async(InventoryService.get_low_stock_items)()


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


# ============================================================================
# Purchase Order Tools
# ============================================================================

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
async def confirm_purchase_order(po_id: int) -> Dict[str, Any]:
    """Confirm a draft purchase order.

    Args:
        po_id: The integer ID of the purchase order.
    """
    return await sync_to_async(PurchaseOrderService.confirm_purchase_order)(po_id=po_id)


# ============================================================================
# HR Leave Tools
# ============================================================================

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
