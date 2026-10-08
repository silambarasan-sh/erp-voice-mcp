# Changelog

All notable changes to the **ERP Voice Agent** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.7.0] - 2026-10-08

### Fixed
- **Chat Intent Routing & Fallback Handling**:
  - Replaced indiscriminate default return of the daily ERP briefing on unrecognized input with a polite capabilities fallback.
  - Added explicit conversational intents:
    - `greeting`: Handles greetings (`hello`, `hi`, `hey`, `vanakkam`) with a welcoming message and 3 concrete example questions.
    - `thanks`: Handles closing remarks (`thanks`, `thank you`, `ok`, `okay`, `bye`) with a polite acknowledgment and no payload data.
    - `help`: Explains assistant capabilities and offers sample queries.
    - `daily_briefing`: Exclusively triggered when the user explicitly requests a briefing, summary, overview, or status.
  - Added structured fallback for unrecognized/gibberish/off-topic inputs listing supported operations (invoices, stock, leaves, restock, top customers) with 2 sample queries.
  - Preserved all existing ERP domain tool intents, `planner_mode` transparency badges, and honesty labels.
  - Added 7 dedicated pytest tests in `tests/test_web_chat.py`.

## [1.6.0] - 2026-10-08

### Added
- **Standalone Package `django-erp-mcp`**:
  - Extracted core reusable Django-to-MCP model adapter into `django-erp-mcp/`.
  - Includes `pyproject.toml` with MIT License, dependencies, and build config.
  - `@mcp_model` decorator and `DjangoMCPRegistry` for declarative tool exposure.
  - Automatic query (`query_<model>`) and fetch (`get_<model>`) MCP tool generation.
  - Complete standalone package test suite (`django-erp-mcp/tests/test_adapter.py`) and standalone example (`django-erp-mcp/example/`).
  - Standalone package `README.md` with quickstart, API documentation, and architecture.
- **Developer Friction Log (`docs/FRICTION_LOG.md`)**:
  - Standardized friction log template (`task`, `steps`, `expected vs actual`, `severity`, `workaround`, `suggestion`).
  - Cataloged 5 engineering friction entries covering MCP protocol header negotiation, SQLite concurrency under async Starlette, Web Speech API nuances, Bedrock test costs, and Django model introspection.
- **Finalized Documentation & Under 5 Commands Run Workflow**:
  - Main `README.md` updated with system architecture (Mermaid flowchart), under 5 commands setup and run guide, step-by-step hackathon demo script, and complete testing instructions.

## [1.5.0] - 2026-10-08

### Added
- **Alexa+ Web Chat Simulator Interface (`/chat` & `/`)**:
  - Embedded web client served directly by the Starlette ASGI application providing a full visual fallback demo for Alexa+.
  - **Voice Input**: Integrates browser **Web Speech API** (`webkitSpeechRecognition`) with pulsing glowing mic animations.
  - **Voice Output**: Integrates browser **`speechSynthesis`** with volume/mute controls and real-time audio wave visualizers.
  - **Interactive Result Cards**:
    - *Invoice Table Card*: Detailed invoices with customer, currency amount (INR), status badges, and overdue indicators.
    - *Low-Stock List Card*: Shortage items, stock vs reorder level progress, supplier lead times, and one-click restocking button.
    - *PO Draft Card with Confirm Button*: Displays drafted orders with an inline **Confirm Purchase Order** button that updates SQLite state and transforms into an emerald confirmed pill.
    - *Leave Requests Card*: Actionable cards with inline **Approve** and **Reject** buttons.
    - *Amazon Bedrock Plan Card*: Multi-step plan execution trace timeline with model tags and confirmation trigger.
- **REST & Web Bridge API (`/api/chat` & `/api/tool`)**:
  - `/api/chat`: Natural language intent router linking user speech/text to MCP tools.
  - `/api/tool`: Direct tool execution bridge enabling UI card buttons to invoke MCP tools.
- **Pytest Web Suite (`tests/test_web_chat.py`)**:
  - Tests covering HTML template rendering, root endpoint browser redirection, replenishment intent routing, invoice querying, voice confirmation, and direct tool calling.

## [1.4.0] - 2026-10-08

### Added
- **AWS Layer for AWS Builder Challenge (Amazon Bedrock & Strands Agents SDK)**:
  - Added `aws_planner` module integrating Amazon Bedrock Foundation Models (`amazon.nova-micro-v1:0` / `anthropic.claude-3-5-sonnet-20241022-v2:0`) and AWS Strands Agents SDK (`strands-agents`).
  - Added `plan_erp_replenishment(prompt, session_id)` MCP tool that accepts natural language instructions (e.g. *"Restock everything that's running low from the fastest supplier"*).
  - Multi-step planning engine: queries warehouse inventory, evaluates supplier lead times, calculates replenishment quantities, creates DRAFT purchase orders, and stages the plan in session state for confirmation.
- **Zero-Cost Mock Mode (`AWS_MOCK_MODE`) & Secure Configuration**:
  - Secure credential chain: reads `AWS_REGION` and `BEDROCK_MODEL_ID` from `.env`, never hardcoding credentials.
  - Added `AWS_MOCK_MODE=True` environment flag to allow comprehensive testing and local demonstrations without requiring active AWS accounts or incurring cloud costs.
- **AWS Usage Documentation (`docs/AWS_USAGE.md`)**:
  - Exhaustive documentation detailing every AWS service utilized (Amazon Bedrock, AWS Strands Agents SDK, Amazon ECS/App Runner, AWS IAM), architectural diagrams, sequence flows, and justification.
- **Dedicated Test Suite (`tests/test_aws_planner.py`)**:
  - Validates environment configuration, fastest supplier selection, multi-step plan generation, draft PO creation, end-to-end *"confirm it"* workflow, and edge case handling.

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
