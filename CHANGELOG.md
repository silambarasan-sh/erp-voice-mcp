# Changelog

All notable changes to the **ERP Voice Agent** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-10-08

### Added
- **Action Tools with Ask-Then-Confirm Pattern**:
  - `draft_purchase_order(item_skus: optional)`: Auto-picks low-stock items below reorder level, groups by supplier, creates DRAFT POs in SQLite, and returns a spoken summary with a `draft_id`. Never changes status to confirmed without explicit confirmation.
  - `confirm_purchase_order(draft_id: optional)`: Explicit confirmation step that transitions draft POs to confirmed. Supports omitting `draft_id` to confirm the active draft stored in session state. Fails politely if no draft exists.
  - `approve_leave(employee_name, confirm: optional)`: Ask-then-confirm pattern for leave approvals. When `confirm=False`, checks pending request and asks for confirmation without altering database status; when `confirm=True`, sets status to `approved`.
  - `reject_leave(employee_name, reason, confirm: optional)`: Ask-then-confirm pattern for leave rejections with reason.
  - `confirm_action()`: Universal handler for conversational "confirm it" intents that automatically executes whichever draft PO or leave action is pending in the session.
- **Conversational Session State & Follow-Up Context**:
  - Added `VoiceSessionService` tracking per-session contexts, last drafts, pending actions, and query history.
  - `get_top_customers()`: Enables follow-up questions such as *"and who are the top 3 customers for that?"* after checking pending invoices, sales summaries, or overdue invoices.
  - Full session isolation across concurrent user sessions.
- **Pytest Action & Session Test Suite (`tests/test_action_confirmation.py`)**:
  - Tests covering draft-only behavior, draft-then-confirm flow, confirming via session state without ID, polite failure when no draft exists, leave approval and rejection ask-then-confirm patterns, top customer follow-up context, and session isolation.

## [1.2.0] - 2026-10-08

### Added
- **5 Voice-Optimized MCP Tools for Alexa+**:
  - `get_pending_invoices(month: optional)`: Returns pending invoice count, total pending amount (INR), and top 3 pending customers.
  - `get_overdue_invoices()`: Returns list of overdue invoices with customer names, days overdue, and amounts.
  - `get_low_stock_items()`: Returns items below reorder level with current quantities, thresholds, and suppliers.
  - `get_pending_leaves()`: Returns pending employee leave requests with employee names, dates, and reasons.
  - `get_sales_summary(period: today|week|month)`: Returns total sales revenue, paid invoice counts, and period breakdown.
- **Speech-Friendly Response Contract**:
  - Every tool returns a concise, conversational `speech` field formatted for text-to-speech engines (Alexa+), paired with an exhaustive `data` field for display/structured processing.
- **Dedicated Pytest Suite (`tests/test_voice_mcp_tools.py`)**:
  - Tests calling all 5 tools covering default arguments, optional month filtering, periods (today, week, month), and data structures.
- **MCP Inspector Integration**:
  - Full instructions for running and testing against Streamable HTTP using `@modelcontextprotocol/inspector`.

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
