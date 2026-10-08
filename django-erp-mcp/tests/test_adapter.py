"""Tests for django-erp-mcp adapter and registry."""

import pytest
from mcp.server.mcpserver import MCPServer
from erp_core.models import Customer, Invoice
from django_erp_mcp.adapter import MCPModelAdapter
from django_erp_mcp.registry import DjangoMCPRegistry
from django_erp_mcp.decorators import mcp_model


@pytest.mark.django_db
def test_adapter_serialization_and_query():
    """Verify MCPModelAdapter serializes model records and respects search fields."""
    Customer.objects.create(name="Tata Motors", city="Pune")
    Customer.objects.create(name="Reliance Industries", city="Mumbai")

    adapter = MCPModelAdapter(
        model=Customer,
        read_fields=["name", "city"],
        search_fields=["name", "city"],
        voice_formatter=lambda items: f"Found {len(items)} customer companies.",
    )

    result = adapter.query_records(search="Motors", limit=5)
    assert "speech" in result
    assert "data" in result
    assert "Found" in result["speech"]
    assert result["data"]["count"] == 1
    assert any("Motors" in r["name"] for r in result["data"]["records"])


@pytest.mark.django_db
def test_adapter_get_record():
    """Verify MCPModelAdapter retrieves a single record by primary key."""
    customer = Customer.objects.create(name="Infosys Technologies", city="Bengaluru")

    adapter = MCPModelAdapter(model=Customer)
    res = adapter.get_record(record_id=customer.id)
    assert res["data"]["found"] is True
    assert res["data"]["record"]["name"] == "Infosys Technologies"

    # Non-existent ID
    res_missing = adapter.get_record(record_id=99999)
    assert res_missing["data"]["found"] is False


def test_registry_registers_tools_on_mcp_server():
    """Verify DjangoMCPRegistry binds query and get tools to MCPServer instance."""
    server = MCPServer("test-django-mcp")
    registry = DjangoMCPRegistry(server)

    adapter = registry.register_model(
        model=Customer,
        read_fields=["name", "city"],
        search_fields=["name"],
    )

    tool_names = [t.name for t in server._tool_manager.list_tools()]
    assert "query_customer" in tool_names
    assert "get_customer" in tool_names
    assert registry.get_adapter("customer") is adapter


def test_mcp_model_decorator():
    """Verify @mcp_model decorator attaches model to registry seamlessly."""
    server = MCPServer("test-decorator-mcp")
    registry = DjangoMCPRegistry(server)

    @mcp_model(registry=registry, search_fields=["invoice_no"])
    class DecoratedModel(Invoice):
        class Meta:
            proxy = True
            app_label = "erp_core"

    tool_names = [t.name for t in server._tool_manager.list_tools()]
    assert "query_decoratedmodel" in tool_names
    assert "get_decoratedmodel" in tool_names
