"""Tests for the seed_demo_data management command."""

import pytest
from django.core.management import call_command
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


@pytest.mark.django_db
def test_seed_demo_data_command():
    """Verify seed_demo_data creates exact expected demo records."""
    call_command("seed_demo_data")

    # 1. 5 Suppliers
    assert Supplier.objects.count() == 5
    for supplier in Supplier.objects.all():
        assert supplier.name
        assert supplier.phone.startswith("+91")
        assert supplier.lead_time_days > 0

    # 2. 10 Customers
    assert Customer.objects.count() == 10
    for customer in Customer.objects.all():
        assert customer.name
        assert customer.city in [
            "Bengaluru", "Pune", "Mumbai", "Chennai",
            "Vadodara", "Hyderabad", "Gurugram", "Delhi",
        ]

    # 3. 25 Items with some below reorder level
    assert Item.objects.count() == 25
    low_stock_items = [item for item in Item.objects.all() if item.is_below_reorder_level]
    assert len(low_stock_items) >= 5, "Expected multiple items below reorder level"
    for item in Item.objects.all():
        assert item.sku.startswith("SKU-IND-")
        assert item.supplier is not None

    # 4. 30 Invoices
    assert Invoice.objects.count() == 30
    paid_count = Invoice.objects.filter(status="paid").count()
    pending_count = Invoice.objects.filter(status="pending").count()
    overdue_count = Invoice.objects.filter(status="overdue").count()
    assert paid_count > 0
    assert pending_count > 0
    assert overdue_count > 0
    assert paid_count + pending_count + overdue_count == 30

    # 5. Purchase Orders and Lines
    assert PurchaseOrder.objects.count() >= 3
    assert PurchaseOrderLine.objects.count() >= 6

    # 6. 15 Employees
    assert Employee.objects.count() == 15
    for emp in Employee.objects.all():
        assert emp.name
        assert emp.department in [
            "Engineering", "Operations", "Finance",
            "Human Resources", "Sales",
        ]

    # 7. 8 Pending Leave Requests
    assert LeaveRequest.objects.filter(status="pending").count() == 8


@pytest.mark.django_db
def test_seed_demo_data_is_idempotent():
    """Verify running seed_demo_data repeatedly cleanly resets and reseeds records."""
    call_command("seed_demo_data")
    call_command("seed_demo_data")

    assert Supplier.objects.count() == 5
    assert Customer.objects.count() == 10
    assert Item.objects.count() == 25
    assert Invoice.objects.count() == 30
    assert Employee.objects.count() == 15
    assert LeaveRequest.objects.filter(status="pending").count() == 8
