# django-erp-mcp 🔌🐍

> A lightweight adapter allowing **any Django application** to expose its models and business logic as **Model Context Protocol (MCP)** tools with speech-friendly summaries and ask-then-confirm action guards.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-4.2%2B-green.svg)](https://www.djangoproject.com/)
[![MCP](https://img.shields.io/badge/MCP-Spec%202025--11--25-blue.svg)](https://modelcontextprotocol.io)

---

## 💡 What is django-erp-mcp?

Voice assistants (Alexa+, Siri, ChatGPT, Claude) need structured tool calling and short speech summaries to interact with business backends.

`django-erp-mcp` bridges **Django ORM** and **Anthropic's Model Context Protocol (MCP)** with zero boilerplate:
- ⚡ **Instant Model Exposure**: Register any Django model to automatically generate `query_<model>` and `get_<model>` tools.
- 🎙️ **Speech-Friendly Summaries**: Formats voice responses in natural spoken sentences with currency/count phrasing.
- 🛡️ **Ask-Then-Confirm Pattern**: Built-in confirmation safety so AI agents never alter databases without explicit approval.
- 🔍 **ORM Search & Filtering**: Automatic case-insensitive multi-field search (`__icontains`) and query expressions.

---

## 📦 Installation

```bash
pip install django-erp-mcp
```

Or install from source:
```bash
git clone https://github.com/silambarasan-sh/erp-voice-mcp.git
cd erp-voice-mcp/django-erp-mcp
pip install -e .
```

---

## 🚀 Quickstart

### 1. Register Models with the Registry

```python
from mcp.server.mcpserver import MCPServer
from django_erp_mcp import DjangoMCPRegistry
from myapp.models import Customer, Invoice

# 1. Initialize your MCP server
mcp_server = MCPServer("my-django-mcp")

# 2. Attach the Django MCP Registry
registry = DjangoMCPRegistry(mcp_server)

# 3. Register your Django models
registry.register_model(
    model=Customer,
    read_fields=["name", "city"],
    search_fields=["name", "city"],
    voice_formatter=lambda customers: f"Found {len(customers)} customer accounts in the system.",
)

registry.register_model(
    model=Invoice,
    read_fields=["invoice_no", "amount", "status", "due_date"],
    search_fields=["invoice_no", "customer__name"],
    voice_formatter=lambda invoices: (
        f"Found {len(invoices)} invoices totaling ₹{sum(inv.amount for inv in invoices):,.2f}."
    ),
)
```

The MCP server will now automatically register and expose:
- `query_customer(search, limit)`
- `get_customer(record_id)`
- `query_invoice(search, limit)`
- `get_invoice(record_id)`

---

## 🎨 Decorator Syntax

You can also use the `@mcp_model` decorator directly on your Django models:

```python
from django.db import models
from django_erp_mcp import mcp_model
from my_mcp_config import registry

@mcp_model(
    registry=registry,
    read_fields=["sku", "name", "stock_qty", "reorder_level"],
    search_fields=["sku", "name"],
    voice_formatter=lambda items: f"Found {len(items)} items in the warehouse inventory.",
)
class InventoryItem(models.Model):
    sku = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    stock_qty = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=10)
```

---

## 🧪 Testing

Run pytest within the package directory:
```bash
pytest tests/
```

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.
