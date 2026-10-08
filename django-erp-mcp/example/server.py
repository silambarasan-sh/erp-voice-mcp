"""Example server illustrating how to expose Django models to any MCP client."""

from mcp.server.mcpserver import MCPServer
from django_erp_mcp import DjangoMCPRegistry
from example.models import Customer, Invoice

# 1. Initialize MCP Server instance
mcp_server = MCPServer("my-django-erp-mcp")

# 2. Attach Django MCP Registry
registry = DjangoMCPRegistry(mcp_server)

# 3. Register Customer model
registry.register_model(
    model=Customer,
    read_fields=["name", "city"],
    search_fields=["name", "city"],
    voice_formatter=lambda customers: f"Found {len(customers)} customer accounts.",
)

# 4. Register Invoice model
registry.register_model(
    model=Invoice,
    read_fields=["invoice_no", "amount", "status", "due_date"],
    search_fields=["invoice_no", "customer__name"],
    voice_formatter=lambda invoices: (
        f"You have {len(invoices)} invoices matching the query. "
        f"Total amount is ₹{sum(inv.amount for inv in invoices):,.2f}."
    ),
)

# The MCP server now automatically exposes:
# - query_customer(search, limit)
# - get_customer(record_id)
# - query_invoice(search, limit)
# - get_invoice(record_id)
if __name__ == "__main__":
    print("MCP Server ready with registered Django model tools!")
