# ERP Voice Agent 🎙️🏢

> **Hackathon Project**: An MCP server that enables **Alexa+** to interact with a sample ERP system (Invoices, Inventory, Purchase Orders, and HR Leave) via natural voice conversations.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Spec](https://img.shields.io/badge/MCP%20Spec-2025--11--25-blue.svg)](https://modelcontextprotocol.io)
[![Django](https://img.shields.io/badge/Django-5.2-green.svg)](https://www.djangoproject.com/)
[![AWS Bedrock](https://img.shields.io/badge/AWS-Bedrock%20%2B%20Strands-orange.svg)](docs/AWS_USAGE.md)
[![Tests](https://img.shields.io/badge/pytest-55%20passed-brightgreen.svg)]()

---

## ☁️ AWS Builder Layer: Amazon Bedrock & Strands Planner

Built for the **AWS Builder Challenge**, this layer integrates **Amazon Bedrock Foundation Models** (`amazon.nova-micro-v1:0` / `anthropic.claude-3-5-sonnet-20241022-v2:0`) and the **AWS Strands Agents SDK** (`strands-agents`) to power autonomous multi-step supply chain planning:

- **Tool**: `plan_erp_replenishment(prompt, session_id)`
- **Natural Language Input**: E.g. *"Restock everything that's running low from the fastest supplier"*
- **Multi-Step Execution**:
  1. Inspects low-stock items across warehouse inventory.
  2. Evaluates registered vendor lead times and optimizes for the fastest fulfillment window.
  3. Formulates replenishment order quantities and groups by supplier.
  4. Generates a **DRAFT** Purchase Order in SQLite and stages it in session state.
  5. Returns a voice-ready plan for Alexa+ asking for confirmation (**never modifies data without user approval**).
  6. The user can simply follow up with *"confirm it"* to approve the plan.
- **Zero-Cost Mock Mode**: Set `AWS_MOCK_MODE=True` in `.env` to run all demos and automated tests offline without cloud costs.
- **Detailed AWS Documentation**: Full architecture and service justifications are documented in [docs/AWS_USAGE.md](docs/AWS_USAGE.md).

---

## 🎙️ Alexa+ Voice & Action MCP Tools

The server exposes voice query tools, context follow-ups, and safe action tools featuring an **Ask-Then-Confirm pattern** (the system **never alters data without user confirmation**):

### 1. Information Query & Context Follow-Up Tools
| Tool | Parameters | Spoken Output / Function |
| :--- | :--- | :--- |
| `get_pending_invoices` | `month` *(optional)*, `session_id` | Spoken summary with count, total pending INR amount, and top 3 customers. Stores context in session state. |
| `get_overdue_invoices` | `session_id` | Spoken summary with count, overdue amount, and customers sorted by days overdue. |
| `get_low_stock_items` | *None* | Spoken summary of inventory items below reorder level requiring supplier replenishment. |
| `get_pending_leaves` | *None* | Spoken summary of pending employee leave requests with employee names and dates. |
| `get_sales_summary` | `period` *(`today` \| `week` \| `month`)*, `session_id` | Spoken summary of sales, paid invoices, and revenue collected. |
| `get_top_customers` | `session_id` | Context follow-up for *"and who are the top 3 customers for that?"* using conversational session memory. |
| `plan_erp_replenishment` | `prompt`, `session_id` | Amazon Bedrock & Strands autonomous multi-step replenishment planner. |

### 2. Action Tools with Confirmation Step
| Tool | Parameters | Ask-Then-Confirm Workflow |
| :--- | :--- | :--- |
| `draft_purchase_order` | `item_skus` *(optional)*, `session_id` | Auto-picks low stock items, groups by supplier, creates **DRAFT** POs in SQLite, and returns a summary + `draft_id`. Status remains `draft`. |
| `confirm_purchase_order`| `draft_id` *(optional)*, `session_id` | Transitions draft PO status to **`confirmed`**. If `draft_id` is omitted, uses the active draft from session state. Fails politely if no draft exists. |
| `approve_leave` | `employee_name`, `confirm` *(bool)*, `session_id` | When `confirm=False`, checks request and asks user for confirmation without altering database status. When `confirm=True`, marks status `approved`. |
| `reject_leave` | `employee_name`, `reason`, `confirm` *(bool)*, `session_id` | When `confirm=False`, asks for confirmation. When `confirm=True`, records reason and marks status `rejected`. |
| `confirm_action` | `session_id` | Universal voice handler for conversational *"confirm it"* queries. Executes whichever staged action is pending in the session. |

### Voice Response Structure:
```json
{
  "speech": "You have 10 pending invoices totaling 18 lakh 75 thousand rupees. The top customers are Tata Motors, Infosys, and Reliance.",
  "data": {
    "count": 10,
    "total_amount": 1875000.0,
    "top_customers": [
      {"customer": "Tata Motors", "pending_amount": 750000.0},
      {"customer": "Infosys", "pending_amount": 620000.0},
      {"customer": "Reliance", "pending_amount": 505000.0}
    ]
  }
}
```

---

## 📁 Repository Structure

```text
erp-voice-mcp/
├── erp_core/                     # Unified Django project + app with models
│   ├── management/
│   │   └── commands/
│   │       └── seed_demo_data.py # Realistic Indian demo data generator
│   ├── migrations/               # Database migrations
│   ├── admin.py                  # Django admin registrations
│   ├── apps.py                   # Django app configuration
│   ├── asgi.py                   # ASGI application
│   ├── models.py                 # Core domain models
│   ├── services.py               # Voice-friendly business logic layer
│   ├── settings.py               # Django 5 project settings
│   ├── urls.py                   # URL configuration
│   └── wsgi.py                   # WSGI application
├── mcp_server/                   # MCP Streamable HTTP server
│   ├── __init__.py
│   ├── app.py                    # Starlette ASGI app (/mcp, /health)
│   ├── run.py                    # CLI server launcher
│   └── server.py                 # Registered MCP tools
├── tests/                        # Pytest test suite (37 tests)
│   ├── conftest.py               # Pytest fixtures and test client
│   ├── test_models.py            # Model unit tests
│   ├── test_seed_command.py      # Demo seed verification
│   ├── test_invoices.py          # Invoice service tests
│   ├── test_inventory.py         # Inventory & low stock tests
│   ├── test_purchase_orders.py   # Purchase orders & lines tests
│   ├── test_hr_leave.py          # HR leave requests tests
│   ├── test_voice_tools.py       # Voice briefing & async tool tests
│   └── test_mcp_protocol.py      # MCP 2025-11-25 & Streamable HTTP tests
├── .env.example                  # Environment template
├── .env                          # Local configuration (no hardcoded secrets)
├── .gitignore                    # Git ignore file
├── CHANGELOG.md                  # Project version changelog
├── LICENSE                       # MIT License
├── manage.py                     # Django management entry point
├── pytest.ini                    # Pytest configuration
├── requirements.txt              # Project dependencies
└── README.md                     # Documentation
```

---

## 🗃️ Data Models

The ERP Core application implements the following models:

1. **`Customer`**:
   - `name`: Company / client name
   - `city`: Operating city (e.g., Bengaluru, Mumbai, Pune)
2. **`Supplier`**:
   - `name`: Vendor name
   - `phone`: Contact phone number (e.g., `+91 98201 11223`)
   - `lead_time_days`: Fulfillment lead time
3. **`Item`**:
   - `sku`: Unique inventory code (e.g., `SKU-IND-001`)
   - `name`: Item description
   - `stock_qty`: Current quantity on hand
   - `reorder_level`: Reorder trigger threshold
   - `supplier`: ForeignKey to `Supplier`
   - `is_below_reorder_level`: Property indicating stock shortage
4. **`Invoice`**:
   - `customer`: ForeignKey to `Customer`
   - `invoice_no`: Unique identifier (e.g., `INV-2026-101`)
   - `amount`: Invoice total in INR (Decimal)
   - `status`: `paid`, `pending`, or `overdue`
   - `due_date`: Payment due date
   - `created_at`: Creation timestamp
5. **`PurchaseOrder`**:
   - `supplier`: ForeignKey to `Supplier`
   - `status`: `draft` or `confirmed`
   - `created_at`: Creation timestamp
6. **`PurchaseOrderLine`**:
   - `po`: ForeignKey to `PurchaseOrder`
   - `item`: ForeignKey to `Item`
   - `qty`: Quantity ordered
7. **`Employee`**:
   - `name`: Full employee name
   - `department`: Department (Engineering, Operations, Finance, etc.)
8. **`LeaveRequest`**:
   - `employee`: ForeignKey to `Employee`
   - `from_date`: Start date
   - `to_date`: End date
   - `status`: `pending`, `approved`, or `rejected`
   - `reason`: Leave explanation

---

## 🌐 MCP Protocol & Streamable HTTP Compliance

- **MCP Specification Version**: **`2025-11-25`**
- **Transport**: **Streamable HTTP** mounted at `/mcp`
- **SDK**: Official Anthropic `mcp` Python SDK (v2.3.0)
- **Header Support**: Negotiates and returns `MCP-Protocol-Version: 2025-11-25`

---

## 🚀 Setup & Execution

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
```
*(On Windows PowerShell: `Copy-Item .env.example .env`)*

### 3. Apply Migrations & Seed Demo Data
```bash
python manage.py makemigrations erp_core
python manage.py migrate
python manage.py seed_demo_data
```

The `seed_demo_data` command generates:
- **5 Indian Suppliers** (e.g., Reliance Industrial Polymers, Tata Advanced Components)
- **10 Indian Customers** across major metropolitan hubs (Bengaluru, Mumbai, Pune, Chennai, Delhi)
- **25 Items** (with multiple critical items below reorder levels)
- **30 Invoices** distributed across `paid`, `pending`, and `overdue`
- **15 Employees** across 5 business departments
- **8 Pending Leave Requests** ready for manager sign-off

---

## 🏃 Running the MCP Server

Start the MCP Streamable HTTP server:
```bash
python -m mcp_server.run
```
Or with Uvicorn:
```bash
uvicorn mcp_server.app:app --host 127.0.0.1 --port 8000
```

- **MCP Endpoint**: `http://127.0.0.1:8000/mcp`
- **Health Check**: `http://127.0.0.1:8000/health`
- **Root Info**: `http://127.0.0.1:8000/`

---

## 🧪 Running Tests

Run the complete test suite with pytest:
```bash
python -m pytest -v
```

All **55 tests** validate:
- Models: Customer, Supplier, Item, Invoice, PurchaseOrder, PurchaseOrderLine, Employee, LeaveRequest
- Management command: `seed_demo_data` (counts, data integrity, idempotency)
- Domain services: Invoices, Inventory, POs, HR Leave
- 5 Voice-optimized MCP tools (`get_pending_invoices`, `get_overdue_invoices`, `get_low_stock_items`, `get_pending_leaves`, `get_sales_summary`)
- Action confirmation workflow: draft PO creation, explicit confirmation, polite failure without draft
- Leave approval and rejection ask-then-confirm patterns
- Conversational session state memory and follow-up tools (`get_top_customers`, `confirm_action`)
- **Amazon Bedrock & Strands ERP Planner Agent**: multi-step inventory planning, fastest supplier optimization, draft creation, and confirmation
- MCP protocol spec `2025-11-25` and Streamable HTTP endpoints

---

## 🔍 Testing with MCP Inspector

You can inspect, interact, and test all 5 voice tools using the official **MCP Inspector**:

### Step 1: Start the ERP MCP Server
In your project terminal:
```bash
python -m mcp_server.run
```
*(The server will be running on `http://127.0.0.1:8000/mcp`)*

### Step 2: Launch the MCP Inspector
In a separate terminal, launch the Inspector with npx:
```bash
npx @modelcontextprotocol/inspector
```
Or connect directly to your Streamable HTTP endpoint:
```bash
npx @modelcontextprotocol/inspector http://127.0.0.1:8000/mcp
```

### Step 3: Connect and Test
1. In the Inspector UI, set **Transport Type** to `Streamable HTTP` (or `SSE / HTTP`).
2. Set the URL to: `http://127.0.0.1:8000/mcp`.
3. Click **Connect**.
4. Navigate to the **Tools** tab:
   - You will see all 5 voice tools listed with their full descriptions.
   - Click `get_pending_invoices` and execute with or without `month`.
   - Click `get_overdue_invoices` and review the overdue list.
   - Click `get_low_stock_items` to view shortage alerts.
   - Click `get_pending_leaves` to see pending leaves.
   - Click `get_sales_summary` with `period: "month"` to check sales performance.
5. Verify both the `speech` string (for Alexa+) and the `data` payload.

---

## 📡 Verification Commands

### 1. Check Health & Protocol Spec Version:
```bash
curl -i http://127.0.0.1:8000/health
```

### 2. Streamable HTTP Header Negotiation:
```bash
curl -i -H "MCP-Protocol-Version: 2025-11-25" http://127.0.0.1:8000/mcp
```

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
