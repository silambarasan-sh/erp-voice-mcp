"""Tests for Purchase Order domain services and operations."""

import pytest
from erp_core.models import PurchaseOrder, PurchaseOrderLine, Supplier, Item
from erp_core.services import PurchaseOrderService


@pytest.mark.django_db
def test_list_purchase_orders():
    """Verify listing POs and filtering by status."""
    all_pos = PurchaseOrderService.list_purchase_orders()
    assert all_pos["count"] >= 3
    assert "purchase orders" in all_pos["voice_summary"].lower()

    draft_pos = PurchaseOrderService.list_purchase_orders(status="draft")
    assert draft_pos["count"] >= 1
    for po in draft_pos["purchase_orders"]:
        assert po["status"] == "draft"


@pytest.mark.django_db
def test_create_purchase_order():
    """Verify creating a new purchase order with lines."""
    sup = Supplier.objects.first()
    item1 = Item.objects.first()
    item2 = Item.objects.last()

    order_items = [
        {"sku": item1.sku, "qty": 30},
        {"sku": item2.sku, "qty": 15},
    ]

    res = PurchaseOrderService.create_purchase_order(
        supplier_name=sup.name,
        items=order_items,
    )
    assert res["success"] is True
    po = res["purchase_order"]
    assert po["status"] == "draft"
    assert len(po["line_items"]) == 2
    assert "draft purchase order" in res["voice_summary"].lower()


@pytest.mark.django_db
def test_confirm_purchase_order():
    """Verify confirming a draft purchase order."""
    draft_po = PurchaseOrder.objects.filter(status="draft").first()
    res = PurchaseOrderService.confirm_purchase_order(draft_po.id)
    assert res["success"] is True
    assert res["purchase_order"]["status"] == "confirmed"
    assert "confirmed" in res["voice_summary"].lower()

    draft_po.refresh_from_db()
    assert draft_po.status == "confirmed"


@pytest.mark.django_db
def test_confirm_nonexistent_purchase_order():
    """Verify error on confirming nonexistent PO."""
    res = PurchaseOrderService.confirm_purchase_order(99999)
    assert res["success"] is False
    assert "not found" in res["error"].lower()
