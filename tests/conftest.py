"""Pytest fixtures for ERP Voice Agent tests."""

import os
import pytest
from django.core.management import call_command

# Ensure settings are loaded
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "erp_core.settings")

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


@pytest.fixture(autouse=True)
def setup_erp_data(db):
    """Seed sample ERP demo data before each test."""
    call_command("seed_demo_data")


@pytest.fixture
def sample_customer(db):
    """Return a representative sample customer."""
    return Customer.objects.filter(name="Infosys Tech Labs").first()


@pytest.fixture
def sample_supplier(db):
    """Return a representative sample supplier."""
    return Supplier.objects.filter(name="Tata Advanced Components").first()


@pytest.fixture
def sample_item(db):
    """Return a representative inventory item."""
    return Item.objects.filter(sku="SKU-IND-001").first()


@pytest.fixture
def low_stock_item(db):
    """Return an item below reorder level."""
    return Item.objects.filter(sku="SKU-IND-002").first()


@pytest.fixture
def sample_invoice(db):
    """Return a representative pending invoice."""
    return Invoice.objects.filter(status="pending").first()


@pytest.fixture
def sample_employee(db):
    """Return a representative employee."""
    return Employee.objects.filter(name="Aarav Sharma").first()


@pytest.fixture
def test_client(db):
    """Return a Starlette TestClient managing a fresh ASGI application lifespan."""
    from starlette.testclient import TestClient
    from mcp_server.app import create_app
    with TestClient(create_app()) as client:
        yield client
