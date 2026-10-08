# Hackathon Friction Log 📝🔍

> Comprehensive friction log capturing developer experience challenges, unexpected behaviors, root causes, workarounds, and framework suggestions encountered while building the **ERP Voice Agent** with the official Python MCP SDK, Django 5, Amazon Bedrock, and AWS Strands Agents SDK.

---

## 📋 Friction Entry Template

When logging new developer friction or SDK limitations, use this standard template:

```markdown
### [FRICT-XXX] Title of the Issue

- **Task**: What task or feature was being implemented?
- **Steps**: Exact steps or command line sequence that reproduced the issue.
- **Expected vs Actual**:
  - *Expected*: What was supposed to happen according to documentation or standard conventions.
  - *Actual*: What actually happened (error message, silent failure, unexpected state).
- **Severity**: Low / Medium / High / Critical
- **Workaround**: How the issue was resolved or bypassed in this codebase.
- **Suggestion**: Recommendations for the upstream framework, SDK authors, or tooling maintainers.
```

---

## 🛠️ Logged Friction Entries

### [FRICT-001] Official Python MCP SDK Streamable HTTP Protocol Version Header Negotiation

- **Task**: Implementing compliant Streamable HTTP transport under MCP Specification `2025-11-25`.
- **Steps**:
  1. Mount `mcp_server.streamable_http_app(streamable_http_path="/mcp")` in Starlette ASGI application.
  2. Send HTTP POST / GET requests with header `MCP-Protocol-Version: 2025-11-25`.
  3. Inspect HTTP response headers.
- **Expected vs Actual**:
  - *Expected*: The official SDK should automatically echo negotiated `MCP-Protocol-Version: 2025-11-25` in outgoing HTTP response headers.
  - *Actual*: The ASGI sub-app did not reliably inject `mcp-protocol-version` in all HTTP lifecycle states (such as initialization or error responses).
- **Severity**: High (causes strict MCP clients and inspectors to reject transport negotiation).
- **Workaround**: Implemented `MCPProtocolVersionMiddleware` in `mcp_server/app.py` that intercepts ASGI `http.response.start` and guarantees the `MCP-Protocol-Version: 2025-11-25` header is appended.
- **Suggestion**: The `mcp` Python SDK's `StreamableHTTPSessionManager` should natively include the protocol version header on all HTTP handshake responses.

---

### [FRICT-002] SQLite Table Locks Across Async MCP Tool Execution & Django ORM

- **Task**: Running asynchronous MCP tool calls that modify Django models (`Invoice`, `PurchaseOrder`, `LeaveRequest`).
- **Steps**:
  1. Register async MCP tools using `sync_to_async(VoiceERPToolsService.action)`.
  2. Execute concurrent or sequential tool calls inside `pytest-asyncio` test suites.
- **Expected vs Actual**:
  - *Expected*: SQLite test database should handle read/write queries seamlessly.
  - *Actual*: Intermittent `sqlite3.OperationalError: database is locked` errors during async transaction commits across test threads.
- **Severity**: Medium
- **Workaround**:
  - Applied `@pytest.mark.django_db(transaction=True)` to all asynchronous test functions to enforce atomic transaction rollback per test.
  - Used explicit `transaction.atomic()` blocks around multi-row PO creation and updates.
- **Suggestion**: Django's async ORM documentation should emphasize `transaction=True` requirements when integrating with ASGI background task runners like MCP.

---

### [FRICT-003] Browser Web Speech API Silence Timeouts in Voice UIs

- **Task**: Implementing continuous speech recognition in the Alexa+ Web Chat Simulator.
- **Steps**:
  1. Call `recognition.start()` via `webkitSpeechRecognition`.
  2. User pauses speech for 1-2 seconds while formulating complex business instructions.
- **Expected vs Actual**:
  - *Expected*: The recognizer should wait for complete utterance or manual stop.
  - *Actual*: Browsers (especially Chromium) fire `onend` after ~1.5 seconds of silence, aborting transcription prematurely.
- **Severity**: Medium
- **Workaround**:
  - Added an `onresult` listener that commits the transcript immediately upon pause and submits to `/api/chat`.
  - Added glowing visual indicators (`mic-glow-ring`) so the user clearly sees when the microphone state flips from listening to processing.
- **Suggestion**: Modern browsers should support configurable `speechEndTimeout` parameters in the Web Speech API.

---

### [FRICT-004] Amazon Bedrock Foundation Model Token Costs During CI/CD Testing

- **Task**: Testing multi-step supply chain planning agent in automated pytest runs and offline hackathon evaluations.
- **Steps**:
  1. Run `python -m pytest` in CI pipeline or offline environment without AWS credentials.
  2. Observe Bedrock client initialization attempts.
- **Expected vs Actual**:
  - *Expected*: Tests should run quickly, deterministically, and without cloud costs.
  - *Actual*: Attempting live calls to Bedrock Foundation Models without credentials caused `NoCredentialsError`, while live calls added latency and API costs.
- **Severity**: High
- **Workaround**:
  - Built a zero-cost **Mock Mode** controlled by `AWS_MOCK_MODE=True` in `.env`.
  - In mock mode, `ERPPlannerAgent._plan_and_execute_mock` simulates the exact Bedrock reasoning trace while running against the real local SQLite database.
- **Suggestion**: Foundation model SDKs should offer built-in deterministic offline test harnesses similar to `moto` for AWS services.

---

### [FRICT-005] Reusable Django Model Introspection for Dynamic MCP Tool Signatures

- **Task**: Extracting the reusable adapter into standalone package `django-erp-mcp`.
- **Steps**:
  1. Dynamically inspect Django model fields (`models.Model._meta.fields`).
  2. Construct MCP tool functions with Python docstrings and type annotations.
- **Expected vs Actual**:
  - *Expected*: Python functions dynamically registered with `mcp_server.tool()` should inherit parameter schemas smoothly.
  - *Actual*: Dynamic closures without explicit parameter signatures can confuse MCP schema generators when inspecting `__annotations__`.
- **Severity**: Medium
- **Workaround**:
  - Designed `DjangoMCPRegistry` to expose explicit parameter wrappers (`search: Optional[str] = None`, `limit: int = 10`) with descriptive docstrings formatted for voice agent discovery.
- **Suggestion**: The `mcp` SDK should support explicit `ToolSchema` programmatic registration in addition to Python function inspection decorators.
