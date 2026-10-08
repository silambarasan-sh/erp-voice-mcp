# Changelog

All notable changes to the **ERP Voice Agent** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-10-08

### Added
- **Exact Models Schema**:
  - `Customer(name, city)`
  - `Supplier(name, phone, lead_time_days)`
  - `Item(sku, name, stock_qty, reorder_level, supplier)` with `is_below_reorder_level` property
  - `Invoice(customer, invoice_no, amount, status[paid/pending/overdue], due_date, created_at)`
  - `PurchaseOrder(supplier, status[draft/confirmed], created_at)`
  - `PurchaseOrderLine(po, item, qty)`
  - `Employee(name, department)`
  - `LeaveRequest(employee, from_date, to_date, status[pending/approved/rejected], reason)`
- **Realistic Indian Demo Data Generator**:
  - Added `python manage.py seed_demo_data` management command.
  - Generates 5 Indian suppliers (Reliance Industrial Polymers, Tata Advanced Components, Havells, etc.).
  - Generates 10 Indian customer enterprises across major cities (Bengaluru, Pune, Mumbai, Chennai, etc.).
  - Generates 25 items with realistic SKUs and names, including items below reorder level.
  - Generates 30 invoices across `paid`, `pending`, and `overdue` statuses.
  - Generates 15 Indian employees across departments.
  - Generates 8 pending leave requests awaiting approval.
- **Dedicated Test Suites**:
  - `tests/test_models.py` covering model operations, relationships, and serialization for all 8 models.
  - `tests/test_seed_command.py` verifying exact seed counts and idempotency.
- **Unified Architecture**:
  - Consolidated `erp_core/` as both the Django project settings and domain app.

## [1.0.0] - 2026-10-08

### Added
- **MCP Server over Streamable HTTP**:
  - Implemented compliant Model Context Protocol (MCP) server supporting spec version `2025-11-25`.
  - Streamable HTTP ASGI transport mounted at `/mcp`.
  - Protocol header negotiation with `MCP-Protocol-Version: 2025-11-25`.
  - Health check endpoint at `/health` and discovery at `/`.
- **Alexa+ Voice Tools**:
  - `voice_daily_erp_briefing` synthesizing cross-domain executive updates into spoken summaries.
  - Invoices, Inventory, Purchase Orders, and HR Leave voice query/action tools.
- **MIT License & Environment Security**:
  - Added MIT License file and `.env.example` template with zero hardcoded credentials.
