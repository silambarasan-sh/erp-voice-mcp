"""Tests for Invoice domain services and operations."""

import pytest
from datetime import date, timedelta
from erp_core.models import Invoice
from erp_core.services import InvoiceService


@pytest.mark.django_db
def test_get_unpaid_invoices_returns_correct_count_and_total():
    """Verify get_unpaid_invoices sums pending and overdue invoices."""
    res = InvoiceService.get_unpaid_invoices()
    # In seeded 30 invoices, unpaid = pending + overdue
    expected_unpaid = Invoice.objects.filter(status__in=["pending", "overdue"]).count()
    assert res["count"] == expected_unpaid
    assert res["total_amount"] > 0
    assert "unpaid invoices" in res["voice_summary"].lower()
    assert len(res["invoices"]) == expected_unpaid


@pytest.mark.django_db
def test_get_unpaid_invoices_filters_by_customer():
    """Verify filtering unpaid invoices by customer name."""
    res = InvoiceService.get_unpaid_invoices(customer_name="Infosys")
    assert res["count"] > 0
    assert any("Infosys" in inv["customer_name"] for inv in res["invoices"])


@pytest.mark.django_db
def test_get_invoice_details_existing_and_non_existing():
    """Verify fetching invoice details by invoice_no."""
    inv = Invoice.objects.first()
    found = InvoiceService.get_invoice_details(inv.invoice_no)
    assert found["success"] is True
    assert found["invoice"]["invoice_no"] == inv.invoice_no
    assert inv.invoice_no in found["voice_summary"]

    missing = InvoiceService.get_invoice_details("INV-NONEXISTENT")
    assert missing["success"] is False
    assert "could not find" in missing["voice_summary"].lower()


@pytest.mark.django_db
def test_create_invoice_success():
    """Verify creating a new invoice."""
    today = date.today()
    due = (today + timedelta(days=14)).isoformat()
    res = InvoiceService.create_invoice(
        customer_name="Tata Consultancy Services",
        amount=55000.00,
        due_date_str=due,
        city="Mumbai",
    )
    assert res["success"] is True
    inv = res["invoice"]
    assert inv["customer_name"] == "Tata Consultancy Services"
    assert inv["amount"] == 55000.00
    assert inv["status"] == "pending"
    assert "Tata Consultancy Services" in res["voice_summary"]


@pytest.mark.django_db
def test_create_invoice_invalid_date():
    """Verify error handling on invalid due date format."""
    res = InvoiceService.create_invoice(
        customer_name="Test Customer",
        amount=100.0,
        due_date_str="invalid-date",
    )
    assert res["success"] is False
    assert "YYYY-MM-DD" in res["error"]


@pytest.mark.django_db
def test_mark_invoice_paid():
    """Verify marking an invoice as paid updates status."""
    inv = Invoice.objects.filter(status="pending").first()
    res = InvoiceService.mark_invoice_paid(inv.invoice_no)
    assert res["success"] is True
    assert res["invoice"]["status"] == "paid"
    assert "paid" in res["voice_summary"].lower()

    # Verify database state
    inv.refresh_from_db()
    assert inv.status == "paid"
