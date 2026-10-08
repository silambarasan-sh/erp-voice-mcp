"""Business logic and service layer for the ERP Voice Agent.

Provides domain services with natural voice summaries tailored for Alexa+ voice interactions,
operating on Customer, Supplier, Item, Invoice, PurchaseOrder, and LeaveRequest models.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from django.db import transaction
from django.utils import timezone

from erp_core.models import (
    Customer,
    Supplier,
    Item,
    Invoice,
    PurchaseOrder,
    PurchaseOrderLine,
    Employee,
    LeaveRequest,
)


class InvoiceService:
    """Service handling invoice queries and status modifications."""

    @staticmethod
    def get_unpaid_invoices(customer_name: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve unpaid (pending or overdue) invoices with a voice-friendly summary."""
        qs = Invoice.objects.filter(status__in=["pending", "overdue"]).select_related("customer")
        if customer_name:
            qs = qs.filter(customer__name__icontains=customer_name)

        invoices = list(qs)
        total_amount = sum((inv.amount for inv in invoices), Decimal("0.00"))
        count = len(invoices)
        overdue_count = sum(1 for inv in invoices if inv.status == "overdue")

        if count == 0:
            voice_summary = "All invoices are cleared. There are no pending or overdue invoices."
        elif count == 1:
            inv = invoices[0]
            voice_summary = (
                f"There is 1 unpaid invoice: {inv.invoice_no} for {inv.customer.name} "
                f"amounting to {inv.amount:,.2f} rupees, due on {inv.due_date}."
            )
        else:
            voice_summary = (
                f"You have {count} unpaid invoices totaling {total_amount:,.2f} rupees, "
                f"with {overdue_count} currently overdue."
            )

        return {
            "count": count,
            "overdue_count": overdue_count,
            "total_amount": float(total_amount),
            "voice_summary": voice_summary,
            "invoices": [inv.to_dict() for inv in invoices],
        }

    @staticmethod
    def get_invoice_details(invoice_no: str) -> Dict[str, Any]:
        """Fetch details for a specific invoice."""
        try:
            inv = Invoice.objects.select_related("customer").get(invoice_no__iexact=invoice_no.strip())
            voice_summary = (
                f"Invoice {inv.invoice_no} for {inv.customer.name} in {inv.customer.city} is {inv.status} "
                f"for {inv.amount:,.2f} rupees, due on {inv.due_date}."
            )
            return {"success": True, "invoice": inv.to_dict(), "voice_summary": voice_summary}
        except Invoice.DoesNotExist:
            return {
                "success": False,
                "error": f"Invoice {invoice_no} not found.",
                "voice_summary": f"I could not find invoice {invoice_no}.",
            }

    @staticmethod
    def create_invoice(
        customer_name: str,
        amount: float,
        due_date_str: str,
        invoice_no: Optional[str] = None,
        city: str = "Mumbai",
    ) -> Dict[str, Any]:
        """Create a new invoice in the ERP."""
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        except ValueError:
            return {
                "success": False,
                "error": "Invalid due_date format. Please use YYYY-MM-DD.",
                "voice_summary": "Invoice creation failed: due date must be in YYYY-MM-DD format.",
            }

        # Retrieve or create customer
        customer, _ = Customer.objects.get_or_create(
            name=customer_name.strip(),
            defaults={"city": city},
        )

        if not invoice_no:
            next_num = Invoice.objects.count() + 101
            invoice_no = f"INV-2026-{next_num}"

        inv = Invoice.objects.create(
            customer=customer,
            invoice_no=invoice_no,
            amount=Decimal(str(amount)),
            status="pending",
            due_date=due_date,
        )
        voice_summary = (
            f"Created invoice {inv.invoice_no} for {customer.name} "
            f"for {inv.amount:,.2f} rupees, due on {inv.due_date}."
        )
        return {"success": True, "invoice": inv.to_dict(), "voice_summary": voice_summary}

    @staticmethod
    def mark_invoice_paid(invoice_no: str) -> Dict[str, Any]:
        """Mark an invoice as paid."""
        try:
            inv = Invoice.objects.select_related("customer").get(invoice_no__iexact=invoice_no.strip())
            inv.status = "paid"
            inv.save()
            voice_summary = f"Invoice {inv.invoice_no} for {inv.customer.name} has been marked as paid."
            return {"success": True, "invoice": inv.to_dict(), "voice_summary": voice_summary}
        except Invoice.DoesNotExist:
            return {
                "success": False,
                "error": f"Invoice {invoice_no} not found.",
                "voice_summary": f"Could not find invoice {invoice_no} to mark as paid.",
            }


class InventoryService:
    """Service handling items, stock checks, and low-stock alerts."""

    @staticmethod
    def check_stock(query: Optional[str] = None) -> Dict[str, Any]:
        """Check warehouse stock levels by SKU or item name."""
        qs = Item.objects.select_related("supplier").all()
        if query:
            qs = qs.filter(sku__icontains=query) | qs.filter(name__icontains=query)

        items = list(qs)
        count = len(items)
        if count == 0:
            return {
                "count": 0,
                "items": [],
                "voice_summary": f"No items matched '{query}'." if query else "Inventory is empty.",
            }

        if count == 1:
            item = items[0]
            voice_summary = (
                f"{item.name} currently has {item.stock_qty} units in stock. "
                f"Reorder level is {item.reorder_level} units."
            )
        else:
            voice_summary = (
                f"Found {count} inventory items. First item is {items[0].name} "
                f"with {items[0].stock_qty} units in stock."
            )

        return {
            "count": count,
            "voice_summary": voice_summary,
            "items": [item.to_dict() for item in items],
        }

    @staticmethod
    def get_low_stock_items() -> Dict[str, Any]:
        """Retrieve items where stock_qty is less than or equal to reorder_level."""
        all_items = Item.objects.select_related("supplier").all()
        low_stock = [item for item in all_items if item.is_below_reorder_level]
        count = len(low_stock)

        if count == 0:
            voice_summary = "All inventory items are currently above reorder thresholds."
        elif count == 1:
            item = low_stock[0]
            voice_summary = (
                f"Warning: {item.name} is low on stock with only {item.stock_qty} units left "
                f"(reorder level: {item.reorder_level}). Supplier: {item.supplier.name}."
            )
        else:
            names = ", ".join(i.name for i in low_stock[:3])
            voice_summary = (
                f"Alert: {count} items are at or below reorder level, including {names}. "
                "Consider creating purchase orders."
            )

        return {
            "count": count,
            "voice_summary": voice_summary,
            "low_stock_items": [item.to_dict() for item in low_stock],
        }

    @staticmethod
    def adjust_stock(sku: str, quantity_delta: int) -> Dict[str, Any]:
        """Adjust physical stock level up or down for a specific SKU."""
        try:
            item = Item.objects.select_related("supplier").get(sku__iexact=sku.strip())
            new_qty = item.stock_qty + quantity_delta
            if new_qty < 0:
                return {
                    "success": False,
                    "error": f"Cannot reduce stock below 0. Current stock is {item.stock_qty}.",
                    "voice_summary": f"Adjustment rejected: only {item.stock_qty} units are in stock.",
                }

            item.stock_qty = new_qty
            item.save()
            action = "increased" if quantity_delta >= 0 else "decreased"
            voice_summary = (
                f"Stock for {item.name} has been {action} by {abs(quantity_delta)}. "
                f"New quantity on hand is {item.stock_qty}."
            )
            return {"success": True, "item": item.to_dict(), "voice_summary": voice_summary}
        except Item.DoesNotExist:
            return {
                "success": False,
                "error": f"Item with SKU {sku} does not exist.",
                "voice_summary": f"I could not find SKU {sku}.",
            }


class PurchaseOrderService:
    """Service handling purchase orders and procurement lines."""

    @staticmethod
    def list_purchase_orders(status: Optional[str] = None) -> Dict[str, Any]:
        """List purchase orders optionally filtered by status ('draft' or 'confirmed')."""
        qs = PurchaseOrder.objects.select_related("supplier").prefetch_related("lines__item").all()
        if status:
            qs = qs.filter(status__iexact=status.strip())

        orders = list(qs)
        count = len(orders)
        draft_count = sum(1 for po in orders if po.status == "draft")

        if count == 0:
            voice_summary = f"No purchase orders found with status '{status}'." if status else "No purchase orders found."
        else:
            voice_summary = (
                f"Found {count} purchase orders. There are {draft_count} draft orders pending confirmation."
            )

        return {
            "count": count,
            "voice_summary": voice_summary,
            "purchase_orders": [po.to_dict() for po in orders],
        }

    @staticmethod
    def create_purchase_order(supplier_name: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a new purchase order with line items.

        items: List of dicts, e.g. [{'sku': 'SKU-IND-001', 'qty': 20}]
        """
        supplier = Supplier.objects.filter(name__icontains=supplier_name.strip()).first()
        if not supplier:
            return {
                "success": False,
                "error": f"Supplier '{supplier_name}' not found.",
                "voice_summary": f"Cannot create purchase order because supplier {supplier_name} was not found.",
            }

        with transaction.atomic():
            po = PurchaseOrder.objects.create(supplier=supplier, status="draft")
            lines_created = []
            for entry in items:
                sku = entry.get("sku")
                qty = entry.get("qty", 1)
                item = Item.objects.filter(sku__iexact=sku).first()
                if item:
                    line = PurchaseOrderLine.objects.create(po=po, item=item, qty=qty)
                    lines_created.append(line)

            voice_summary = (
                f"Created draft purchase order #{po.id} for {supplier.name} "
                f"with {len(lines_created)} line items."
            )
            return {"success": True, "purchase_order": po.to_dict(), "voice_summary": voice_summary}

    @staticmethod
    def confirm_purchase_order(po_id: int) -> Dict[str, Any]:
        """Confirm a draft purchase order."""
        try:
            po = PurchaseOrder.objects.select_related("supplier").get(id=po_id)
            po.status = "confirmed"
            po.save()
            voice_summary = f"Purchase order #{po.id} for {po.supplier.name} is now confirmed."
            return {"success": True, "purchase_order": po.to_dict(), "voice_summary": voice_summary}
        except PurchaseOrder.DoesNotExist:
            return {
                "success": False,
                "error": f"Purchase order #{po_id} not found.",
                "voice_summary": f"Could not find purchase order #{po_id}.",
            }


class HRLeaveService:
    """Service handling employees and leave requests."""

    @staticmethod
    def get_employee_leave_summary(employee_query: str) -> Dict[str, Any]:
        """Look up employee details and recent leave requests."""
        q = employee_query.strip()
        emp = Employee.objects.filter(name__icontains=q).prefetch_related("leave_requests").first()
        if not emp:
            return {
                "success": False,
                "error": f"Employee '{employee_query}' not found.",
                "voice_summary": f"I could not find any employee named {employee_query}.",
            }

        requests = list(emp.leave_requests.all())
        pending_count = sum(1 for r in requests if r.status == "pending")

        voice_summary = (
            f"{emp.name} works in {emp.department}. "
            f"They have {pending_count} pending leave requests out of {len(requests)} total requests."
        )
        return {
            "success": True,
            "employee": emp.to_dict(),
            "leave_requests": [r.to_dict() for r in requests],
            "voice_summary": voice_summary,
        }

    @staticmethod
    def request_leave(
        employee_name: str,
        from_date_str: str,
        to_date_str: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Submit a new employee leave request."""
        emp = Employee.objects.filter(name__icontains=employee_name.strip()).first()
        if not emp:
            return {
                "success": False,
                "error": f"Employee '{employee_name}' not found.",
                "voice_summary": f"Could not submit leave request: employee {employee_name} was not found.",
            }

        try:
            f_date = datetime.strptime(from_date_str, "%Y-%m-%d").date()
            t_date = datetime.strptime(to_date_str, "%Y-%m-%d").date()
        except ValueError:
            return {
                "success": False,
                "error": "Dates must be in YYYY-MM-DD format.",
                "voice_summary": "Leave request rejected: dates must be in Year-Month-Day format.",
            }

        leave_req = LeaveRequest.objects.create(
            employee=emp,
            from_date=f_date,
            to_date=t_date,
            status="pending",
            reason=reason,
        )
        voice_summary = (
            f"Submitted leave request for {emp.name} from {leave_req.from_date} "
            f"to {leave_req.to_date}. Status is pending approval."
        )
        return {"success": True, "leave_request": leave_req.to_dict(), "voice_summary": voice_summary}

    @staticmethod
    def list_pending_leave_requests() -> Dict[str, Any]:
        """List all pending leave requests requiring manager review."""
        pending = list(LeaveRequest.objects.filter(status="pending").select_related("employee"))
        count = len(pending)
        if count == 0:
            voice_summary = "There are no pending employee leave requests."
        elif count == 1:
            req = pending[0]
            voice_summary = (
                f"There is 1 pending leave request from {req.employee.name} ({req.employee.department}) "
                f"from {req.from_date} to {req.to_date}."
            )
        else:
            voice_summary = f"There are {count} pending employee leave requests awaiting manager review."

        return {
            "count": count,
            "voice_summary": voice_summary,
            "pending_requests": [req.to_dict() for req in pending],
        }

    @staticmethod
    def decide_leave_request(request_id: int, approve: bool = True) -> Dict[str, Any]:
        """Approve or reject a leave request."""
        try:
            req = LeaveRequest.objects.select_related("employee").get(id=request_id)
            req.status = "approved" if approve else "rejected"
            req.save()
            action = "approved" if approve else "rejected"
            voice_summary = f"Leave request #{req.id} for {req.employee.name} has been {action}."
            return {"success": True, "leave_request": req.to_dict(), "voice_summary": voice_summary}
        except LeaveRequest.DoesNotExist:
            return {
                "success": False,
                "error": f"Leave request #{request_id} not found.",
                "voice_summary": f"Could not find leave request #{request_id}.",
            }


class VoiceBriefingService:
    """Service generating aggregated voice briefings for Alexa+."""

    @staticmethod
    def get_daily_briefing() -> Dict[str, Any]:
        """Generate executive briefing covering Indian ERP state."""
        unpaid = Invoice.objects.filter(status__in=["pending", "overdue"])
        unpaid_count = unpaid.count()
        unpaid_total = sum((inv.amount for inv in unpaid), Decimal("0.00"))

        low_stock_items = [i for i in Item.objects.all() if i.is_below_reorder_level]
        low_stock_count = len(low_stock_items)

        draft_pos = PurchaseOrder.objects.filter(status="draft").count()
        pending_leave = LeaveRequest.objects.filter(status="pending").count()

        voice_summary = (
            f"Namaste! Here is your daily ERP briefing. "
            f"You have {unpaid_count} unpaid invoices totaling {unpaid_total:,.2f} rupees. "
            f"{low_stock_count} items are below reorder level. "
            f"{draft_pos} draft purchase orders and {pending_leave} leave requests are awaiting your review."
        )

        return {
            "timestamp": timezone.now().isoformat(),
            "unpaid_invoices_count": unpaid_count,
            "unpaid_invoices_total": float(unpaid_total),
            "low_stock_count": low_stock_count,
            "draft_purchase_orders_count": draft_pos,
            "pending_leave_requests_count": pending_leave,
            "voice_summary": voice_summary,
        }
