"""Business logic and service layer for the ERP Voice Agent.

Provides domain services with natural voice summaries tailored for Alexa+ voice interactions,
operating on Customer, Supplier, Item, Invoice, PurchaseOrder, and LeaveRequest models.
"""

from datetime import date, datetime, timedelta
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


class VoiceSessionService:
    """Manages conversational session state and pending confirmations for voice agents."""

    _sessions: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_session(cls, session_id: str = "default") -> Dict[str, Any]:
        """Retrieve session state dict by session_id."""
        sid = session_id or "default"
        if sid not in cls._sessions:
            cls._sessions[sid] = {
                "last_context": None,
                "context_data": {},
                "last_draft_id": None,
                "last_draft_po_ids": [],
                "pending_action": None,
            }
        return cls._sessions[sid]

    @classmethod
    def set_context(
        cls,
        session_id: str = "default",
        context_type: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store context type and relevant query data in the session."""
        s = cls.get_session(session_id)
        s["last_context"] = context_type
        if data:
            s["context_data"] = data

    @classmethod
    def set_pending_action(
        cls,
        session_id: str = "default",
        action_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store a staged action awaiting explicit user confirmation."""
        s = cls.get_session(session_id)
        s["pending_action"] = action_data

    @classmethod
    def get_pending_action(cls, session_id: str = "default") -> Optional[Dict[str, Any]]:
        """Retrieve the currently pending action awaiting confirmation."""
        return cls.get_session(session_id).get("pending_action")

    @classmethod
    def clear_pending_action(cls, session_id: str = "default") -> None:
        """Clear any pending action from the session."""
        s = cls.get_session(session_id)
        s["pending_action"] = None

    @classmethod
    def reset(cls, session_id: Optional[str] = None) -> None:
        """Reset session data. If session_id is None, clears all sessions."""
        if session_id:
            cls._sessions.pop(session_id, None)
        else:
            cls._sessions.clear()


class VoiceERPToolsService:
    """Service implementing core Alexa+ ERP voice tools with speech-friendly responses and session state."""

    MONTH_MAP = {
        "january": 1, "jan": 1, "1": 1, "01": 1,
        "february": 2, "feb": 2, "2": 2, "02": 2,
        "march": 3, "mar": 3, "3": 3, "03": 3,
        "april": 4, "apr": 4, "4": 4, "04": 4,
        "may": 5, "5": 5, "05": 5,
        "june": 6, "jun": 6, "6": 6, "06": 6,
        "july": 7, "jul": 7, "7": 7, "07": 7,
        "august": 8, "aug": 8, "8": 8, "08": 8,
        "september": 9, "sep": 9, "sept": 9, "9": 9, "09": 9,
        "october": 10, "oct": 10, "10": 10,
        "november": 11, "nov": 11, "11": 11,
        "december": 12, "dec": 12, "12": 12,
    }

    @classmethod
    def get_pending_invoices(cls, month: Optional[str] = None, session_id: str = "default") -> Dict[str, Any]:
        """Return pending invoices with count, total amount, and top 3 customers.

        Optionally filtered by month name or number. Saves context to session state.
        """
        qs = Invoice.objects.filter(status="pending").select_related("customer")
        month_label = ""

        if month:
            cleaned = month.strip().lower()
            month_num = None
            if "-" in cleaned:
                parts = cleaned.split("-")
                try:
                    month_num = int(parts[1])
                    qs = qs.filter(due_date__year=int(parts[0]), due_date__month=month_num)
                    month_label = f" for {cleaned}"
                except (ValueError, IndexError):
                    pass
            elif cleaned in cls.MONTH_MAP:
                month_num = cls.MONTH_MAP[cleaned]
                qs = qs.filter(due_date__month=month_num)
                month_label = f" for {month.capitalize()}"

        invoices = list(qs)
        count = len(invoices)
        total_amount = sum((inv.amount for inv in invoices), Decimal("0.00"))

        # Calculate top 3 customers by amount
        cust_totals: Dict[str, Decimal] = {}
        for inv in invoices:
            name = inv.customer.name
            cust_totals[name] = cust_totals.get(name, Decimal("0.00")) + inv.amount

        sorted_customers = sorted(cust_totals.items(), key=lambda x: x[1], reverse=True)[:3]
        top_3 = [{"customer": name, "amount": float(amt)} for name, amt in sorted_customers]

        # Update session state for context follow-up
        VoiceSessionService.set_context(
            session_id=session_id,
            context_type="pending_invoices",
            data={
                "month": month,
                "count": count,
                "total_amount": float(total_amount),
                "top_customers": top_3,
            },
        )

        if count == 0:
            speech = f"You have no pending invoices{month_label}."
        else:
            top_2_names = ", ".join(name for name, _ in sorted_customers[:2])
            speech = (
                f"You have {count} pending invoices{month_label} totaling {total_amount:,.2f} rupees. "
                f"Top customers are {top_2_names}. The full list is on your screen."
            )

        return {
            "speech": speech,
            "data": {
                "count": count,
                "total_amount": float(total_amount),
                "month_filter": month,
                "top_3_customers": top_3,
                "invoices": [inv.to_dict() for inv in invoices],
            },
        }

    @classmethod
    def get_overdue_invoices(cls, session_id: str = "default") -> Dict[str, Any]:
        """Return overdue invoices with customer name and number of days overdue."""
        today = timezone.now().date()
        qs = Invoice.objects.filter(status="overdue").select_related("customer").order_by("due_date")
        invoices = list(qs)
        count = len(invoices)

        overdue_list = []
        total_amount = Decimal("0.00")
        cust_totals: Dict[str, Decimal] = {}

        for inv in invoices:
            days = max(0, (today - inv.due_date).days)
            total_amount += inv.amount
            name = inv.customer.name
            cust_totals[name] = cust_totals.get(name, Decimal("0.00")) + inv.amount
            overdue_list.append({
                "invoice_no": inv.invoice_no,
                "customer": inv.customer.name,
                "amount": float(inv.amount),
                "due_date": inv.due_date.isoformat(),
                "days_overdue": days,
            })

        overdue_list.sort(key=lambda x: x["days_overdue"], reverse=True)
        sorted_customers = sorted(cust_totals.items(), key=lambda x: x[1], reverse=True)[:3]
        top_3 = [{"customer": name, "amount": float(amt)} for name, amt in sorted_customers]

        VoiceSessionService.set_context(
            session_id=session_id,
            context_type="overdue_invoices",
            data={
                "count": count,
                "total_amount": float(total_amount),
                "top_customers": top_3,
            },
        )

        if count == 0:
            speech = "Great news, there are no overdue invoices."
        else:
            top_2_overdue = overdue_list[:2]
            top_2_desc = ", and ".join(
                f"{inv['invoice_no']} for {inv['customer']} ({inv['days_overdue']} days overdue)"
                for inv in top_2_overdue
            )
            speech = (
                f"You have {count} overdue invoices totaling {total_amount:,.2f} rupees, "
                f"including {top_2_desc}. The full list is on your screen."
            )

        return {
            "speech": speech,
            "data": {
                "count": count,
                "total_amount": float(total_amount),
                "invoices": overdue_list,
            },
        }

    @staticmethod
    def get_low_stock_items() -> Dict[str, Any]:
        """Return inventory items currently below reorder level requiring restocking."""
        all_items = Item.objects.select_related("supplier").all()
        low_items = [i for i in all_items if i.is_below_reorder_level]
        low_items.sort(key=lambda x: x.stock_qty)
        count = len(low_items)

        items_data = [
            {
                "sku": i.sku,
                "name": i.name,
                "stock_qty": i.stock_qty,
                "reorder_level": i.reorder_level,
                "supplier": i.supplier.name,
                "lead_time_days": i.supplier.lead_time_days,
            }
            for i in low_items
        ]

        if count == 0:
            speech = "All inventory items are currently well-stocked above reorder levels."
        else:
            sample_names = ", ".join(i.name for i in low_items[:2])
            speech = (
                f"There are {count} items below reorder level, including {sample_names}. "
                "The full list is on your screen."
            )

        return {
            "speech": speech,
            "data": {
                "count": count,
                "items": items_data,
            },
        }

    @staticmethod
    def get_pending_leaves() -> Dict[str, Any]:
        """Return employee leave requests pending manager review with dates and departments."""
        requests = list(LeaveRequest.objects.filter(status="pending").select_related("employee").order_by("from_date"))
        count = len(requests)

        leaves_data = [
            {
                "id": r.id,
                "employee": r.employee.name,
                "department": r.employee.department,
                "from_date": r.from_date.isoformat(),
                "to_date": r.to_date.isoformat(),
                "reason": r.reason,
            }
            for r in requests
        ]

        if count == 0:
            speech = "There are no pending employee leave requests."
        elif count == 1:
            req = leaves_data[0]
            speech = (
                f"There is 1 pending leave request from {req['employee']} in {req['department']} "
                f"from {req['from_date']} to {req['to_date']}. The full list is on your screen."
            )
        else:
            first_two = [f"{r['employee']} from {r['from_date']}" for r in leaves_data[:2]]
            names_summary = ", and ".join(first_two)
            speech = (
                f"You have {count} pending leave requests, including {names_summary}. "
                "The full list is on your screen."
            )

        return {
            "speech": speech,
            "data": {
                "count": count,
                "pending_leaves": leaves_data,
            },
        }

    @classmethod
    def get_sales_summary(cls, period: str = "month", session_id: str = "default") -> Dict[str, Any]:
        """Return total sales revenue and invoice counts for today, this week, or this month."""
        cleaned = period.strip().lower()
        today = timezone.now().date()

        if cleaned == "today":
            start_date = today
            period_label = "today"
        elif cleaned == "week":
            start_date = today - timedelta(days=7)
            period_label = "this week"
        else:
            start_date = today - timedelta(days=30)
            period_label = "this month"
            cleaned = "month"

        qs = Invoice.objects.filter(created_at__date__gte=start_date).select_related("customer")
        invoices = list(qs)

        total_invoiced = sum((inv.amount for inv in invoices), Decimal("0.00"))
        total_count = len(invoices)

        paid_invoices = [inv for inv in invoices if inv.status == "paid"]
        paid_amount = sum((inv.amount for inv in paid_invoices), Decimal("0.00"))
        paid_count = len(paid_invoices)

        pending_invoices = [inv for inv in invoices if inv.status == "pending"]
        pending_amount = sum((inv.amount for inv in pending_invoices), Decimal("0.00"))

        overdue_invoices = [inv for inv in invoices if inv.status == "overdue"]
        overdue_amount = sum((inv.amount for inv in overdue_invoices), Decimal("0.00"))

        # Compute top customers for the sales period
        cust_sales: Dict[str, Decimal] = {}
        target_invoices = paid_invoices if paid_invoices else invoices
        for inv in target_invoices:
            name = inv.customer.name
            cust_sales[name] = cust_sales.get(name, Decimal("0.00")) + inv.amount
        sorted_sales = sorted(cust_sales.items(), key=lambda x: x[1], reverse=True)[:3]
        sales_top_3 = [{"customer": name, "amount": float(amt)} for name, amt in sorted_sales]

        VoiceSessionService.set_context(
            session_id=session_id,
            context_type="sales_summary",
            data={
                "period": cleaned,
                "period_label": period_label,
                "top_customers": sales_top_3,
            },
        )

        speech = (
            f"Sales summary for {period_label}: {total_count} invoices created totaling {total_invoiced:,.2f} rupees, "
            f"with {paid_amount:,.2f} rupees collected from {paid_count} paid invoices."
        )

        return {
            "speech": speech,
            "data": {
                "period": cleaned,
                "period_label": period_label,
                "start_date": start_date.isoformat(),
                "total_invoices_count": total_count,
                "total_invoiced_amount": float(total_invoiced),
                "paid_invoices_count": paid_count,
                "paid_amount": float(paid_amount),
                "pending_invoices_count": len(pending_invoices),
                "pending_amount": float(pending_amount),
                "overdue_invoices_count": len(overdue_invoices),
                "overdue_amount": float(overdue_amount),
            },
        }

    @classmethod
    def get_purchase_order_status(cls, session_id: str = "default") -> Dict[str, Any]:
        """Query purchase order status breakdown including draft vs confirmed counts and latest orders.

        Reuses PurchaseOrderService.list_purchase_orders to avoid duplicate logic.
        """
        po_result = PurchaseOrderService.list_purchase_orders()
        orders = po_result.get("purchase_orders", [])
        total_count = len(orders)
        draft_count = sum(1 for po in orders if po.get("status") == "draft")
        confirmed_count = sum(1 for po in orders if po.get("status") == "confirmed")

        # Latest few orders (up to 5) with supplier and item count
        recent_orders = []
        for po in orders[:5]:
            lines = po.get("line_items", [])
            total_qty = sum(item.get("qty", 0) for item in lines)
            recent_orders.append({
                "id": po.get("id"),
                "supplier": po.get("supplier_name"),
                "status": po.get("status"),
                "created_at": po.get("created_at"),
                "item_count": len(lines),
                "total_quantity": total_qty,
            })

        if total_count == 0:
            speech = "There are no purchase orders in the system."
        elif draft_count > 0:
            speech = (
                f"You have {total_count} purchase orders: {draft_count} in draft status waiting for confirmation, "
                f"and {confirmed_count} confirmed."
            )
        else:
            speech = f"You have {total_count} purchase orders, all {confirmed_count} are confirmed."

        data = {
            "total_count": total_count,
            "draft_count": draft_count,
            "confirmed_count": confirmed_count,
            "recent_orders": recent_orders,
            "purchase_orders": orders,
        }

        VoiceSessionService.set_context(
            session_id=session_id,
            context_type="purchase_order_status",
            data=data,
        )

        return {
            "speech": speech,
            "data": data,
        }

    # =========================================================================
    # Action Tools with Confirmation & Session Follow-Up
    # =========================================================================

    @classmethod
    def get_top_customers(cls, session_id: str = "default") -> Dict[str, Any]:
        """Follow-up tool when the user asks 'and who are the top 3 customers for that?'.

        Retrieves top customers from the current conversational session context.
        """
        session = VoiceSessionService.get_session(session_id)
        last_context = session.get("last_context")
        ctx_data = session.get("context_data", {})
        top_3 = ctx_data.get("top_customers", [])

        if not top_3 and not last_context:
            # Fallback to current pending invoices
            qs = Invoice.objects.filter(status="pending").select_related("customer")
            cust_totals: Dict[str, Decimal] = {}
            for inv in qs:
                name = inv.customer.name
                cust_totals[name] = cust_totals.get(name, Decimal("0.00")) + inv.amount
            sorted_cust = sorted(cust_totals.items(), key=lambda x: x[1], reverse=True)[:3]
            top_3 = [{"customer": name, "amount": float(amt)} for name, amt in sorted_cust]
            last_context = "pending_invoices"

        if not top_3:
            speech = "I couldn't find any customer balances for that context."
        else:
            names_str = ", ".join(f"{c['customer']} ({c['amount']:,.2f} rupees)" for c in top_3)
            context_labels = {
                "pending_invoices": f"pending invoices{(' for ' + ctx_data.get('month')) if ctx_data.get('month') else ''}",
                "sales_summary": f"sales for {ctx_data.get('period_label', 'the period')}",
                "overdue_invoices": "overdue invoices",
            }
            ctx_label = context_labels.get(last_context, "that query")
            speech = f"For your {ctx_label}, the top 3 customers are {names_str}."

        return {
            "speech": speech,
            "data": {
                "context": last_context,
                "top_customers": top_3,
            },
        }

    @classmethod
    def draft_purchase_order(
        cls,
        item_skus: Optional[List[str]] = None,
        session_id: str = "default",
    ) -> Dict[str, Any]:
        """Auto-picks low-stock items, groups by supplier, creates DRAFT POs, and returns summary + draft_id.

        Never alters status to confirmed without an explicit confirmation step.
        """
        if item_skus:
            items = list(Item.objects.filter(sku__in=item_skus).select_related("supplier"))
            if not items:
                return {
                    "speech": "No inventory items were found matching the provided SKUs.",
                    "data": {
                        "success": False,
                        "error": "No items found for provided SKUs",
                    },
                }
        else:
            all_items = Item.objects.select_related("supplier").all()
            items = [i for i in all_items if i.is_below_reorder_level]
            if not items:
                return {
                    "speech": "All inventory items are currently above their reorder level. No draft purchase orders are needed.",
                    "data": {
                        "count": 0,
                        "draft_id": None,
                        "po_ids": [],
                    },
                }

        # Group items by supplier
        supplier_map: Dict[Any, List[Item]] = {}
        for item in items:
            supplier_map.setdefault(item.supplier, []).append(item)

        created_pos: List[PurchaseOrder] = []
        total_qty = 0

        with transaction.atomic():
            for supplier, sup_items in supplier_map.items():
                po = PurchaseOrder.objects.create(supplier=supplier, status="draft")
                for it in sup_items:
                    order_qty = max(it.reorder_level * 2 - it.stock_qty, it.reorder_level, 10)
                    PurchaseOrderLine.objects.create(po=po, item=it, qty=order_qty)
                    total_qty += order_qty
                created_pos.append(po)

        primary_id = created_pos[0].id
        draft_id = f"DRAFT-PO-{primary_id}"
        po_ids = [p.id for p in created_pos]
        supplier_names = [s.name for s in supplier_map.keys()]

        # Store draft info in session state for follow-up and confirmation
        session = VoiceSessionService.get_session(session_id)
        session["last_draft_id"] = draft_id
        session["last_draft_po_ids"] = po_ids

        VoiceSessionService.set_context(
            session_id=session_id,
            context_type="draft_purchase_order",
            data={
                "draft_id": draft_id,
                "po_ids": po_ids,
                "suppliers": supplier_names,
            },
        )
        VoiceSessionService.set_pending_action(
            session_id=session_id,
            action_data={
                "type": "confirm_purchase_order",
                "draft_id": draft_id,
                "po_ids": po_ids,
                "suppliers": supplier_names,
            },
        )

        sup_names_str = ", ".join(supplier_names)
        speech = (
            f"I have created draft purchase orders for {len(supplier_map)} suppliers ({sup_names_str}) "
            f"covering {len(items)} low stock items with draft ID {draft_id}. Total quantity: {total_qty}. "
            f"Would you like me to confirm them?"
        )

        return {
            "speech": speech,
            "data": {
                "draft_id": draft_id,
                "status": "draft",
                "requires_confirmation": True,
                "po_count": len(created_pos),
                "po_ids": po_ids,
                "suppliers": supplier_names,
                "items_count": len(items),
                "total_quantity": total_qty,
                "items": [
                    {"sku": it.sku, "name": it.name, "supplier": it.supplier.name}
                    for it in items
                ],
            },
        }

    @classmethod
    def confirm_purchase_order(
        cls,
        draft_id: Optional[str] = None,
        session_id: str = "default",
    ) -> Dict[str, Any]:
        """Confirm a draft purchase order. Only here does status become confirmed.

        If draft_id is omitted, checks session state for the last draft.
        Fails politely if no draft purchase order exists.
        """
        import re

        session = VoiceSessionService.get_session(session_id)
        resolved_draft_id = draft_id or session.get("last_draft_id")
        po_ids = []

        if not resolved_draft_id:
            return {
                "speech": "There is no pending draft purchase order to confirm. Would you like me to create a draft first?",
                "data": {
                    "success": False,
                    "error": "No draft purchase order found to confirm.",
                },
            }

        # Check if the requested draft matches the session's batch
        if resolved_draft_id == session.get("last_draft_id") and session.get("last_draft_po_ids"):
            po_ids = session.get("last_draft_po_ids", [])
        else:
            # Extract numeric id from string e.g. 'DRAFT-PO-5' or '5'
            nums = re.findall(r"\d+", str(resolved_draft_id))
            po_ids = [int(n) for n in nums] if nums else []

        if not po_ids:
            return {
                "speech": f"I couldn't find draft purchase order {resolved_draft_id}. Would you like me to check existing orders?",
                "data": {
                    "success": False,
                    "error": f"Invalid draft purchase order ID: {resolved_draft_id}",
                },
            }

        pos = list(PurchaseOrder.objects.filter(id__in=po_ids).select_related("supplier"))
        if not pos:
            return {
                "speech": f"I couldn't find any purchase orders matching {resolved_draft_id}.",
                "data": {
                    "success": False,
                    "error": f"No purchase order found for {resolved_draft_id}",
                },
            }

        if all(p.status == "confirmed" for p in pos):
            return {
                "speech": f"Purchase order {resolved_draft_id} is already confirmed.",
                "data": {
                    "success": False,
                    "status": "already_confirmed",
                    "draft_id": resolved_draft_id,
                },
            }

        confirmed_ids = []
        supplier_names = set()

        with transaction.atomic():
            for po in pos:
                if po.status == "draft":
                    po.status = "confirmed"
                    po.save(update_fields=["status"])
                    confirmed_ids.append(po.id)
                    supplier_names.add(po.supplier.name)

        VoiceSessionService.clear_pending_action(session_id)

        sup_names_str = ", ".join(sorted(supplier_names))
        speech = f"Purchase order {resolved_draft_id} for {sup_names_str} has been confirmed."

        return {
            "speech": speech,
            "data": {
                "success": True,
                "draft_id": resolved_draft_id,
                "status": "confirmed",
                "confirmed_po_ids": confirmed_ids,
                "suppliers": sorted(supplier_names),
            },
        }

    @classmethod
    def approve_leave(
        cls,
        employee_name: str,
        confirm: bool = False,
        session_id: str = "default",
    ) -> Dict[str, Any]:
        """Approve an employee leave request using an ask-then-confirm workflow.

        Never modifies database status without confirm=True.
        """
        leave = (
            LeaveRequest.objects.filter(
                employee__name__icontains=employee_name.strip(),
                status="pending",
            )
            .select_related("employee")
            .order_by("from_date")
            .first()
        )
        if not leave:
            return {
                "speech": f"I couldn't find any pending leave request for {employee_name}.",
                "data": {
                    "success": False,
                    "error": f"No pending leave found for {employee_name}",
                },
            }

        emp_name = leave.employee.name
        date_range = f"{leave.from_date} to {leave.to_date}"
        reason_str = f" for '{leave.reason}'" if leave.reason else ""

        if not confirm:
            VoiceSessionService.set_pending_action(
                session_id=session_id,
                action_data={
                    "type": "approve_leave",
                    "employee_name": emp_name,
                    "leave_id": leave.id,
                    "date_range": date_range,
                },
            )
            return {
                "speech": f"{emp_name} has requested leave from {date_range}{reason_str}. Should I confirm this approval?",
                "data": {
                    "requires_confirmation": True,
                    "action": "approve_leave",
                    "leave_id": leave.id,
                    "employee": emp_name,
                    "from_date": leave.from_date.isoformat(),
                    "to_date": leave.to_date.isoformat(),
                    "reason": leave.reason,
                },
            }

        # Execute only upon confirmation
        leave.status = "approved"
        leave.save(update_fields=["status"])
        VoiceSessionService.clear_pending_action(session_id)

        return {
            "speech": f"Leave request for {emp_name} from {date_range} has been confirmed and approved.",
            "data": {
                "success": True,
                "status": "approved",
                "leave_id": leave.id,
                "employee": emp_name,
            },
        }

    @classmethod
    def reject_leave(
        cls,
        employee_name: str,
        reason: str = "",
        confirm: bool = False,
        session_id: str = "default",
    ) -> Dict[str, Any]:
        """Reject an employee leave request using an ask-then-confirm workflow.

        Never modifies database status without confirm=True.
        """
        leave = (
            LeaveRequest.objects.filter(
                employee__name__icontains=employee_name.strip(),
                status="pending",
            )
            .select_related("employee")
            .order_by("from_date")
            .first()
        )
        if not leave:
            return {
                "speech": f"I couldn't find any pending leave request for {employee_name}.",
                "data": {
                    "success": False,
                    "error": f"No pending leave found for {employee_name}",
                },
            }

        emp_name = leave.employee.name
        date_range = f"{leave.from_date} to {leave.to_date}"

        if not confirm:
            VoiceSessionService.set_pending_action(
                session_id=session_id,
                action_data={
                    "type": "reject_leave",
                    "employee_name": emp_name,
                    "leave_id": leave.id,
                    "reason": reason,
                    "date_range": date_range,
                },
            )
            reason_phrase = f" with reason '{reason}'" if reason else ""
            return {
                "speech": f"Are you sure you want to reject {emp_name}'s leave request from {date_range}{reason_phrase}? Please confirm.",
                "data": {
                    "requires_confirmation": True,
                    "action": "reject_leave",
                    "leave_id": leave.id,
                    "employee": emp_name,
                    "reason": reason,
                },
            }

        # Execute only upon confirmation
        leave.status = "rejected"
        if reason:
            leave.reason = f"{leave.reason} (Rejected: {reason})" if leave.reason else f"Rejected: {reason}"
        leave.save(update_fields=["status", "reason"])
        VoiceSessionService.clear_pending_action(session_id)

        return {
            "speech": f"Leave request for {emp_name} from {date_range} has been rejected.",
            "data": {
                "success": True,
                "status": "rejected",
                "leave_id": leave.id,
                "employee": emp_name,
                "reason": reason,
            },
        }

    @classmethod
    def confirm_action(cls, session_id: str = "default") -> Dict[str, Any]:
        """Universal confirmation handler for voice intent 'confirm it'.

        Resolves whichever staged action (draft PO, leave approval, leave rejection) is pending.
        """
        pending = VoiceSessionService.get_pending_action(session_id)
        if not pending:
            # Fallback to check if a draft PO was created in this session
            session = VoiceSessionService.get_session(session_id)
            if session.get("last_draft_id"):
                return cls.confirm_purchase_order(draft_id=session.get("last_draft_id"), session_id=session_id)
            return {
                "speech": "There are no pending actions waiting for confirmation. What would you like me to do?",
                "data": {
                    "success": False,
                    "error": "No pending action found in session",
                },
            }

        action_type = pending.get("type")
        if action_type == "confirm_purchase_order":
            return cls.confirm_purchase_order(draft_id=pending.get("draft_id"), session_id=session_id)
        elif action_type == "approve_leave":
            return cls.approve_leave(employee_name=pending.get("employee_name"), confirm=True, session_id=session_id)
        elif action_type == "reject_leave":
            return cls.reject_leave(
                employee_name=pending.get("employee_name"),
                reason=pending.get("reason", ""),
                confirm=True,
                session_id=session_id,
            )

        return {
            "speech": "There are no pending actions waiting for confirmation.",
            "data": {"success": False, "error": f"Unknown action type {action_type}"},
        }

