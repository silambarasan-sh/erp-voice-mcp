"""Tests for Inventory domain services and operations."""

import pytest
from erp_core.models import Item
from erp_core.services import InventoryService


@pytest.mark.django_db
def test_check_stock_all_items():
    """Verify stock check returns all 25 items when no query is provided."""
    res = InventoryService.check_stock()
    assert res["count"] == 25
    assert len(res["items"]) == 25
    assert "inventory items" in res["voice_summary"].lower()


@pytest.mark.django_db
def test_check_stock_by_sku_and_name():
    """Verify searching stock by SKU or partial item name."""
    res_sku = InventoryService.check_stock("SKU-IND-001")
    assert res_sku["count"] == 1
    assert res_sku["items"][0]["sku"] == "SKU-IND-001"
    assert "units in stock" in res_sku["voice_summary"]

    res_name = InventoryService.check_stock("Servo Motor")
    assert res_name["count"] == 1
    assert "Servo Motor" in res_name["items"][0]["name"]


@pytest.mark.django_db
def test_get_low_stock_alerts():
    """Verify low stock alerts identify items at or below reorder level."""
    res = InventoryService.get_low_stock_items()
    assert res["count"] >= 5
    assert len(res["low_stock_items"]) == res["count"]
    assert "below reorder level" in res["voice_summary"].lower()


@pytest.mark.django_db
def test_adjust_stock_increase_and_decrease():
    """Verify adjusting stock up and down."""
    item = Item.objects.filter(sku="SKU-IND-007").first()
    initial_qty = item.stock_qty

    # Increase stock
    up = InventoryService.adjust_stock("SKU-IND-007", 10)
    assert up["success"] is True
    assert up["item"]["stock_qty"] == initial_qty + 10
    assert "increased" in up["voice_summary"].lower()

    # Decrease stock
    down = InventoryService.adjust_stock("SKU-IND-007", -5)
    assert down["success"] is True
    assert down["item"]["stock_qty"] == initial_qty + 5
    assert "decreased" in down["voice_summary"].lower()


@pytest.mark.django_db
def test_adjust_stock_prevents_negative():
    """Verify that adjusting stock below zero fails with validation error."""
    item = Item.objects.filter(sku="SKU-IND-006").first()
    res = InventoryService.adjust_stock("SKU-IND-006", -(item.stock_qty + 10))
    assert res["success"] is False
    assert "below 0" in res["error"]
    assert "rejected" in res["voice_summary"].lower()
