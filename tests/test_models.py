"""Unit tests for ERP Core Django models."""

import pytest
from datetime import date, timedelta
from decimal import Decimal
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
def test_customer_model():
    """Verify Customer model creation, string representation, and serialization."""
    customer = Customer.objects.create(name="Reliance Digital Retail", city="Ahmedabad")
    assert str(customer) == "Reliance Digital Retail (Ahmedabad)"
    data = customer.to_dict()
    assert data["name"] == "Reliance Digital Retail"
    assert data["city"] == "Ahmedabad"
    assert data["id"] == customer.id


@pytest.mark.django_db
def test_supplier_model():
    """Verify Supplier model creation and lead time representation."""
    supplier = Supplier.objects.create(
        name="Larsen Heavy Fab",
        phone="+91 99887 76655",
        lead_time_days=8,
    )
    assert "8 days" in str(supplier)
    data = supplier.to_dict()
    assert data["name"] == "Larsen Heavy Fab"
    assert data["phone"] == "+91 99887 76655"
    assert data["lead_time_days"] == 8


@pytest.mark.django_db
def test_item_model_and_reorder_property():
    """Verify Item model and is_below_reorder_level property calculation."""
    supplier = Supplier.objects.first()
    normal_item = Item.objects.create(
        sku="TEST-SKU-001",
        name="Standard Relay Module",
        stock_qty=50,
        reorder_level=10,
        supplier=supplier,
    )
    assert not normal_item.is_below_reorder_level
    assert normal_item.to_dict()["is_below_reorder_level"] is False

    low_item = Item.objects.create(
        sku="TEST-SKU-002",
        name="Critical Semiconductor",
        stock_qty=3,
        reorder_level=10,
        supplier=supplier,
    )
    assert low_item.is_below_reorder_level
    assert low_item.to_dict()["is_below_reorder_level"] is True
    assert "Critical Semiconductor" in str(low_item)


@pytest.mark.django_db
def test_invoice_model_status_and_relation():
    """Verify Invoice model linked to Customer with status choices."""
    customer = Customer.objects.first()
    today = date.today()
    invoice = Invoice.objects.create(
        customer=customer,
        invoice_no="INV-TEST-999",
        amount=Decimal("12500.50"),
        status="pending",
        due_date=today + timedelta(days=15),
    )
    assert "INV-TEST-999" in str(invoice)
    assert invoice.status == "pending"

    data = invoice.to_dict()
    assert data["invoice_no"] == "INV-TEST-999"
    assert data["customer_name"] == customer.name
    assert data["amount"] == 12500.50
    assert data["status"] == "pending"


@pytest.mark.django_db
def test_purchase_order_and_line_models():
    """Verify PurchaseOrder and PurchaseOrderLine relationship."""
    supplier = Supplier.objects.first()
    item = Item.objects.first()

    po = PurchaseOrder.objects.create(supplier=supplier, status="draft")
    assert f"PO #{po.id}" in str(po)
    assert po.status == "draft"

    line = PurchaseOrderLine.objects.create(po=po, item=item, qty=40)
    assert "40x" in str(line)
    assert line.to_dict()["qty"] == 40
    assert line.to_dict()["item_sku"] == item.sku

    po_dict = po.to_dict()
    assert len(po_dict["line_items"]) == 1
    assert po_dict["supplier_name"] == supplier.name


@pytest.mark.django_db
def test_employee_model():
    """Verify Employee model creation and department."""
    emp = Employee.objects.create(name="Divya Raghavan", department="Quality Assurance")
    assert str(emp) == "Divya Raghavan - Quality Assurance"
    data = emp.to_dict()
    assert data["name"] == "Divya Raghavan"
    assert data["department"] == "Quality Assurance"


@pytest.mark.django_db
def test_leave_request_model():
    """Verify LeaveRequest model linked to Employee."""
    emp = Employee.objects.first()
    today = date.today()
    leave = LeaveRequest.objects.create(
        employee=emp,
        from_date=today + timedelta(days=2),
        to_date=today + timedelta(days=5),
        status="pending",
        reason="Family function attendance",
    )
    assert emp.name in str(leave)
    data = leave.to_dict()
    assert data["employee_name"] == emp.name
    assert data["status"] == "pending"
    assert data["reason"] == "Family function attendance"
