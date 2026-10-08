# AWS Usage & Architecture: ERP Voice Agent ☁️🎙️

> **AWS Builder Challenge Submission**: Comprehensive documentation of AWS cloud services, architectural roles, and design decisions powering the **ERP Voice Agent**.

---

## 🏗️ 1. Architecture Overview

The **ERP Voice Agent** integrates **Amazon Bedrock** and the **AWS Strands Agents SDK** with an enterprise Model Context Protocol (MCP) server over Streamable HTTP, enabling **Alexa+** and executive voice assistants to reason across ERP supply chain operations safely.

```text
                               ┌──────────────────────────────────────────────────┐
                               │                    Alexa+ /                      │
                               │                Voice Assistant                   │
                               └─────────────────────────┬────────────────────────┘
                                                         │ Voice Query
                                                         ▼
                               ┌──────────────────────────────────────────────────┐
                               │           MCP Server (Streamable HTTP)           │
                               │           ASGI Mounted at /mcp (Spec 2025-11-25) │
                               └─────────────────────────┬────────────────────────┘
                                                         │
                                    ┌────────────────────┴────────────────────┐
                                    ▼                                         ▼
                     ┌─────────────────────────────┐           ┌─────────────────────────────┐
                     │   Standard Voice MCP Tools  │           │   AWS Builder Layer:        │
                     │  - Invoices, Stock, Leaves  │           │   Amazon Bedrock & Strands  │
                     │  - Ask-Then-Confirm Actions │           │   ERP Planner Agent         │
                     └──────────────┬──────────────┘           └──────────────┬──────────────┘
                                    │                                         │
                                    │ Multi-Step Planning & Tool Invocations  │
                                    └────────────────────┬────────────────────┘
                                                         │
                                                         ▼
                               ┌──────────────────────────────────────────────────┐
                               │                  ERP Core Layer                  │
                               │           Django 5 + SQLite Database             │
                               │  - Customers, Suppliers, Items, Invoices, POs    │
                               └──────────────────────────────────────────────────┘
```

---

## ☁️ 2. AWS Services Used & Justification

### 1. Amazon Bedrock
- **Role**: Foundation Model Orchestration & Natural Language Reasoning Engine.
- **Models Utilized**:
  - `amazon.nova-micro-v1:0` (Fast, cost-efficient Amazon Nova model for real-time voice latency)
  - `anthropic.claude-3-5-sonnet-20241022-v2:0` (Advanced multi-step reasoning and supplier optimization)
- **Why Bedrock**:
  1. **Serverless Generative AI**: Zero GPU provisioning or infrastructure management.
  2. **Low-Latency Converse API**: Delivers the near-instantaneous responses essential for natural Alexa+ voice interactions.
  3. **Enterprise Data Privacy**: Ensures proprietary business ERP data (invoices, client records, purchase orders) is never used for foundation model training.
  4. **Native Tool Use**: Seamlessly invokes Python functions as tools to inspect stock levels, compare supplier lead times, and generate purchase orders.

### 2. AWS Strands Agents SDK (`strands-agents`)
- **Role**: Official AWS Multi-Agent Framework and Tool Orchestration Layer.
- **Why Strands Agents SDK**:
  1. **First-Class Bedrock Integration**: Built natively around `BedrockModel` with automatic schema generation for Python functions.
  2. **Multi-Step Goal Decomposition**: Transforms vague executive directives (e.g., *"Restock everything running low from the fastest supplier"*) into structured, verifiable execution sequences.
  3. **Safety & Confirmation Enforcement**: Embeds the critical ERP safety constraint that draft orders are staged in session memory and **never committed to the database without explicit user confirmation**.

### 3. AWS App Runner / Amazon ECS (Container Hosting)
- **Role**: Scalable, fully-managed hosting for the Model Context Protocol (MCP) server.
- **Why App Runner / ECS**:
  1. Direct support for streaming ASGI HTTP servers (`Streamable HTTP` on `/mcp`).
  2. Automatic horizontal scaling in response to concurrent voice queries.
  3. Seamless integration with AWS VPC, AWS Secrets Manager, and IAM Roles.

### 4. AWS Identity and Access Management (IAM)
- **Role**: Least-Privilege Role-Based Access Control (RBAC).
- **Policy Definition**:
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "bedrock:InvokeModel",
          "bedrock:Converse"
        ],
        "Resource": [
          "arn:aws:bedrock:*::foundation-model/amazon.nova-micro-v1:0",
          "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
        ]
      }
    ]
  }
  ```
- **Security Rule**: Zero hardcoded credentials. Reads region and model ID from environment variables, leveraging standard AWS credential providers (IAM Roles, AWS CLI profiles, or environment variables).

---

## 🎯 3. The "ERP Planner Agent" Workflow

When an executive speaks an instruction such as:
> *"Restock everything that's running low from the fastest supplier"*

The **ERP Planner Agent** executes a multi-step plan:

```mermaid
sequenceDiagram
    autonumber
    actor User as Executive (Alexa+)
    participant MCP as MCP Server (/mcp)
    participant Bedrock as Amazon Bedrock / Strands
    participant ERP as ERP Database (Django)
    participant Session as VoiceSessionService

    User->>MCP: "Restock everything that's running low from the fastest supplier"
    MCP->>Bedrock: ERPPlannerAgent.plan_and_execute(prompt)
    Bedrock->>ERP: tool_get_low_stock_items()
    ERP-->>Bedrock: Returns 7 low-stock items with supplier details
    Note over Bedrock: Evaluates supplier lead times.<br/>Identifies fastest supplier: Reliance (3 days).
    Bedrock->>ERP: tool_draft_purchase_order(item_skus, status="draft")
    ERP-->>Bedrock: Creates DRAFT PO (ID: DRAFT-PO-11)
    Bedrock->>Session: Stages DRAFT-PO-11 for confirmation
    Bedrock-->>MCP: Voice summary + structured plan data
    MCP-->>User: "Reliance is the fastest supplier (3-day lead time). I drafted order DRAFT-PO-11. Would you like me to confirm it?"
    User->>MCP: "Confirm it"
    MCP->>ERP: confirm_action() -> changes status to confirmed
    ERP-->>User: "Purchase order DRAFT-PO-11 has been confirmed."
```

---

## 🧪 4. Honest & Transparent Planner Modes (`AWS_MOCK_MODE`)

To ensure that hackathon evaluators, CI/CD automated test suites, and local demos can run **without incurring AWS charges or requiring active AWS credentials**, the application includes an honest and transparent multi-mode planner architecture.

Every response from `plan_erp_replenishment` / `ERPPlannerAgent` includes an explicit **`planner_mode`** field:

| Mode | Trigger Condition | Behavior & Guarantees |
| :--- | :--- | :--- |
| **`"bedrock"`** | `AWS_MOCK_MODE=False` and AWS Bedrock Converse API succeeds | Live foundation model call (`amazon.nova-micro-v1:0` or Claude 3.5 Sonnet) reasons over the inventory and formulates replenishment steps. |
| **`"mock"`** | `AWS_MOCK_MODE=True` (Default) | Zero-cost deterministic multi-step simulation executing identical reasoning and tool chains without calling AWS APIs. |
| **`"fallback"`** | `AWS_MOCK_MODE=False` but Bedrock API call fails (credentials, network, quota) | Emits a clear **`WARNING`** log with the exact exception reason, attaches `fallback_reason` to the response, and falls back gracefully to the deterministic local planner so ERP operations remain uninterrupted. |

---

### 🔍 Real vs. Mocked Breakdown in Default Mode

In default mode (`AWS_MOCK_MODE=True`), here is exactly what is real versus what is simulated:

| System Component | Execution Status | Implementation Details |
| :--- | :---: | :--- |
| **Amazon Bedrock Foundation Model** | **Mocked** | Simulated deterministic reasoning trace matching Bedrock execution without invoking AWS billable APIs. |
| **ERP Inventory Database Query** | **100% REAL** | Real Django ORM query (`Item.objects.select_related("supplier").all()`) evaluating live SQLite stock levels against reorder thresholds. |
| **Supplier Lead Time Evaluation** | **100% REAL** | Real calculation comparing supplier lead times (`supplier.lead_time_days`) from the live database. |
| **Purchase Order Creation** | **100% REAL** | Writes actual draft Purchase Order and PO Line records to SQLite via `VoiceERPToolsService.draft_purchase_order()`. |
| **Conversational Session Memory** | **100% REAL** | Real conversational staging in `VoiceSessionService` enabling subsequent spoken *"Confirm it"* queries. |
| **Safety Enforcement (Ask-Then-Confirm)** | **100% REAL** | Drafts strictly remain in `'draft'` status until explicit user confirmation is received. |

---

### Configuration in `.env`:
```ini
# Set to True for zero-cost local demo & pytest suites (Default)
AWS_MOCK_MODE=True

# Set to False to route calls to live Amazon Bedrock
# AWS_MOCK_MODE=False

# AWS Region & Model configuration
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=amazon.nova-micro-v1:0
```

### Transitioning to Live AWS:
To run against real Amazon Bedrock:
1. Set `AWS_MOCK_MODE=False` in `.env`.
2. Configure AWS credentials via `aws configure` or environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`).
3. The server automatically routes requests to Bedrock's Converse API. If credentials are missing or invalid, the server logs a `WARNING` and sets `planner_mode: "fallback"`.

---

### 🎨 Web Chat UI Transparency Guarantee
- **Badge Indicators**: The web chat UI displays a dedicated badge next to every plan result:
  - `<span class="pill pill-confirmed">Bedrock (live)</span>` (Emerald) when live Bedrock succeeded.
  - `<span class="pill pill-draft">Mock mode</span>` (Purple) when in default mock mode.
  - `<span class="pill pill-overdue">Fallback</span>` (Amber) when live Bedrock failed and local planner was used (including an inline notice explaining the fallback reason).
- **Labeling Rules**: Header subtext and Restock button labels **never display "Bedrock"** unless the active mode is verified live.
