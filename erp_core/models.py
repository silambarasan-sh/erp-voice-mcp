"""ERP Core domain models.

Provides models for Customers, Invoices, Suppliers, Items,
Purchase Orders, Purchase Order Lines, Employees, and Leave Requests.
"""

from decimal import Decimal
from typing import Any, Dict
from django.db import models


class Customer(models.Model):
    """Represents a customer or client organization."""

    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.city})"

    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "city": self.city,
        }


class Supplier(models.Model):
    """Represents a raw material or product supplier."""

    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50)
    lead_time_days = models.PositiveIntegerField(default=7)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} (Lead time: {self.lead_time_days} days)"

    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "lead_time_days": self.lead_time_days,
        }


class Item(models.Model):
    """Represents an inventory item or stock keeping unit."""

    sku = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    stock_qty = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=10)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="items")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.sku}) - Qty: {self.stock_qty} (Reorder: {self.reorder_level})"

    @property
    def is_below_reorder_level(self) -> bool:
        """Return True if stock_qty is less than or equal to reorder_level."""
        return self.stock_qty <= self.reorder_level

    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to a dictionary."""
        return {
            "id": self.id,
            "sku": self.sku,
            "name": self.name,
            "stock_qty": self.stock_qty,
            "reorder_level": self.reorder_level,
            "is_below_reorder_level": self.is_below_reorder_level,
            "supplier_id": self.supplier.id,
            "supplier_name": self.supplier.name,
        }


class Invoice(models.Model):
    """Represents a sales invoice billed to a customer."""

    STATUS_CHOICES = [
        ("paid", "Paid"),
        ("pending", "Pending"),
        ("overdue", "Overdue"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="invoices")
    invoice_no = models.CharField(max_length=64, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    due_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-due_date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.invoice_no} - {self.customer.name} (₹{self.amount}) [{self.status}]"

    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to a dictionary."""
        return {
            "id": self.id,
            "customer_id": self.customer.id,
            "customer_name": self.customer.name,
            "customer_city": self.customer.city,
            "invoice_no": self.invoice_no,
            "amount": float(self.amount),
            "status": self.status,
            "due_date": self.due_date.isoformat(),
            "created_at": self.created_at.isoformat(),
        }


class PurchaseOrder(models.Model):
    """Represents a purchase order issued to a supplier."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("confirmed", "Confirmed"),
    ]

    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="purchase_orders")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"PO #{self.id} - {self.supplier.name} [{self.status}]"

    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to a dictionary."""
        return {
            "id": self.id,
            "supplier_id": self.supplier.id,
            "supplier_name": self.supplier.name,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "line_items": [line.to_dict() for line in self.lines.all()],
        }


class PurchaseOrderLine(models.Model):
    """Represents an individual line item inside a purchase order."""

    po = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="po_lines")
    qty = models.PositiveIntegerField()

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"Line: {self.qty}x {self.item.name} for PO #{self.po.id}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to a dictionary."""
        return {
            "id": self.id,
            "item_sku": self.item.sku,
            "item_name": self.item.name,
            "qty": self.qty,
        }


class Employee(models.Model):
    """Represents an employee in an organization."""

    name = models.CharField(max_length=255)
    department = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} - {self.department}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "department": self.department,
        }


class LeaveRequest(models.Model):
    """Represents an employee leave / time off request."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_requests")
    from_date = models.DateField()
    to_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-from_date"]

    def __str__(self) -> str:
        return f"{self.employee.name}: {self.from_date} to {self.to_date} [{self.status}]"

    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to a dictionary."""
        return {
            "id": self.id,
            "employee_id": self.employee.id,
            "employee_name": self.employee.name,
            "department": self.employee.department,
            "from_date": self.from_date.isoformat(),
            "to_date": self.to_date.isoformat(),
            "status": self.status,
            "reason": self.reason,
        }
