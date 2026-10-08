import os
import re
from typing import Callable
import django
from asgiref.sync import sync_to_async
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "erp_core.settings")
django.setup()

from mcp_server.server import mcp_server, SERVER_NAME, SERVER_VERSION

MCP_PATH = os.getenv("MCP_STREAMABLE_HTTP_PATH", "/mcp")
MCP_SPEC_VERSION = os.getenv("MCP_PROTOCOL_VERSION", "2025-11-25")


class MCPProtocolVersionMiddleware:
    """ASGI middleware ensuring MCP-Protocol-Version header is returned on MCP endpoints."""

    def __init__(self, app: ASGIApp, protocol_version: str = MCP_SPEC_VERSION) -> None:
        self.app = app
        self.protocol_version = protocol_version

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                has_pv = any(k.lower() == b"mcp-protocol-version" for k, v in headers)
                if not has_pv:
                    headers.append((b"mcp-protocol-version", self.protocol_version.encode("ascii")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


from pathlib import Path
from starlette.responses import HTMLResponse, JSONResponse
from erp_core.services import VoiceERPToolsService, VoiceBriefingService
from aws_planner.agent import ERPPlannerAgent
from aws_planner.config import AWSConfig

TEMPLATES_DIR = Path(__file__).parent / "templates"
CHAT_HTML_PATH = TEMPLATES_DIR / "chat.html"


async def chat_page(request: Request) -> HTMLResponse:
    """Serve the Alexa+ web chat simulator HTML page with mode-transparent labels."""
    if CHAT_HTML_PATH.exists():
        content = CHAT_HTML_PATH.read_text(encoding="utf-8")
        is_live = not AWSConfig.is_mock_mode()
        header_subtext = (
            "Model Context Protocol &bull; Amazon Bedrock Planner"
            if is_live
            else "Model Context Protocol &bull; Supply Chain Planner"
        )
        restock_label = (
            "⚡ Restock Fastest Supplier (Bedrock)"
            if is_live
            else "⚡ Restock Fastest Supplier"
        )
        content = content.replace("<!--HEADER_PLANNER_SUBTEXT-->", header_subtext)
        content = content.replace("<!--RESTOCK_BUTTON_LABEL-->", restock_label)
        content = content.replace("/*DEFAULT_IS_LIVE*/ false", f"/*DEFAULT_IS_LIVE*/ {'true' if is_live else 'false'}")
    else:
        content = "<h1>Alexa+ ERP Web Chat</h1><p>Template not found.</p>"
    return HTMLResponse(content)


async def chat_api(request: Request) -> JSONResponse:
    """Natural language chat endpoint routing messages to MCP voice tools."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    message = body.get("message", "").strip()
    session_id = body.get("session_id", "default")
    lower = message.lower()

    tool_name = "general"
    response_payload = {}

    if any(k in lower for k in ["confirm", "confirm it", "yes confirm", "proceed"]):
        tool_name = "confirm_action"
        response_payload = await sync_to_async(VoiceERPToolsService.confirm_action)(session_id=session_id)

    elif any(k in lower for k in ["restock", "fastest supplier", "replenish", "plan"]):
        tool_name = "plan_erp_replenishment"
        response_payload = await sync_to_async(ERPPlannerAgent.plan_and_execute)(prompt=message, session_id=session_id)

    elif any(k in lower for k in ["top 3 customer", "top customer", "customers for that"]):
        tool_name = "get_top_customers"
        response_payload = await sync_to_async(VoiceERPToolsService.get_top_customers)(session_id=session_id)

    elif "overdue" in lower:
        tool_name = "get_overdue_invoices"
        response_payload = await sync_to_async(VoiceERPToolsService.get_overdue_invoices)(session_id=session_id)

    elif any(k in lower for k in ["pending invoice", "unpaid invoice", "invoice"]):
        tool_name = "get_pending_invoices"
        month = None
        for m in ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]:
            if m in lower:
                month = m
                break
        response_payload = await sync_to_async(VoiceERPToolsService.get_pending_invoices)(month=month, session_id=session_id)

    elif any(k in lower for k in ["low stock", "shortage", "inventory"]):
        tool_name = "get_low_stock_items"
        response_payload = await sync_to_async(VoiceERPToolsService.get_low_stock_items)()

    elif any(k in lower for k in ["leave", "vacation", "time off"]):
        tool_name = "get_pending_leaves"
        response_payload = await sync_to_async(VoiceERPToolsService.get_pending_leaves)()

    elif any(k in lower for k in ["sales", "revenue"]):
        tool_name = "get_sales_summary"
        period = "today" if "today" in lower else ("week" if "week" in lower else "month")
        response_payload = await sync_to_async(VoiceERPToolsService.get_sales_summary)(period=period, session_id=session_id)

    elif "draft" in lower and ("order" in lower or "po" in lower or "purchase" in lower):
        tool_name = "draft_purchase_order"
        response_payload = await sync_to_async(VoiceERPToolsService.draft_purchase_order)(session_id=session_id)

    elif any(k in lower for k in ["briefing", "daily briefing", "summary", "overview", "status"]):
        # Explicit daily executive briefing request
        tool_name = "voice_daily_erp_briefing"
        briefing = await sync_to_async(VoiceBriefingService.get_daily_briefing)()
        response_payload = {
            "speech": briefing.get("voice_summary", "Here is your ERP briefing."),
            "data": briefing,
        }

    elif any(k in lower for k in ["what can you do", "help", "how can you help", "what do you do", "commands"]):
        tool_name = "help"
        speech = (
            "I can help you monitor and run your business operations. "
            "You can ask me to check pending or overdue invoices, review low stock inventory, "
            "check leave requests, restock items from the fastest supplier, or find your top customers. "
            "For example: 'What are my pending invoices?' or 'Restock everything that's running low'."
        )
        response_payload = {
            "speech": speech,
            "data": {
                "intent": "help",
                "capabilities": ["invoices", "stock", "leaves", "restock", "top customers"],
                "examples": ["What are my pending invoices?", "Restock everything that's running low"],
            },
        }

    elif bool(re.search(r"\b(hello|hi|hey|vanakkam)\b", lower)):
        tool_name = "greeting"
        speech = (
            "Hello! I am your Alexa+ ERP Voice Assistant. "
            "Here are three questions you can ask me: "
            "1. 'What are my pending invoices?' "
            "2. 'Show me low stock items.' "
            "3. 'Restock everything that's running low from the fastest supplier.'"
        )
        response_payload = {
            "speech": speech,
            "data": {
                "intent": "greeting",
                "examples": [
                    "What are my pending invoices?",
                    "Show me low stock items",
                    "Restock everything that's running low from the fastest supplier",
                ],
            },
        }

    elif bool(re.search(r"\b(thanks|thank you|thank u|ok|okay|bye|goodbye)\b", lower)):
        tool_name = "thanks"
        speech = "You're welcome! Let me know whenever you need anything else."
        response_payload = {
            "speech": speech,
            "data": {},
        }

    else:
        # Polite fallback message - never default to the daily briefing
        tool_name = "unrecognized"
        speech = (
            "I'm not sure how to help with that. I can help you with invoices, "
            "stock, leaves, restock, and top customers. For example, you can ask: "
            "'What are my pending invoices?' or 'Show low stock items'."
        )
        response_payload = {
            "speech": speech,
            "data": {
                "intent": "unrecognized",
                "capabilities": ["invoices", "stock", "leaves", "restock", "top customers"],
                "examples": [
                    "What are my pending invoices?",
                    "Show low stock items",
                ],
            },
        }

    res_body = {
        "tool": tool_name,
        "speech": response_payload.get("speech", response_payload.get("voice_summary", "")),
        "data": response_payload.get("data", response_payload),
    }
    if "planner_mode" in response_payload:
        res_body["planner_mode"] = response_payload["planner_mode"]
    if "fallback_reason" in response_payload:
        res_body["fallback_reason"] = response_payload["fallback_reason"]
    return JSONResponse(res_body)


async def tool_api(request: Request) -> JSONResponse:
    """Direct tool invocation API for card interactive buttons."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    tool_name = body.get("tool_name", "")
    args = body.get("arguments", {})
    session_id = body.get("session_id", "default")
    args["session_id"] = session_id

    result = {}
    if tool_name == "confirm_purchase_order":
        result = await sync_to_async(VoiceERPToolsService.confirm_purchase_order)(
            draft_id=args.get("draft_id"),
            session_id=session_id,
        )
    elif tool_name == "draft_purchase_order":
        result = await sync_to_async(VoiceERPToolsService.draft_purchase_order)(
            item_skus=args.get("item_skus"),
            session_id=session_id,
        )
    elif tool_name == "approve_leave":
        result = await sync_to_async(VoiceERPToolsService.approve_leave)(
            employee_name=args.get("employee_name", ""),
            confirm=args.get("confirm", True),
            session_id=session_id,
        )
    elif tool_name == "reject_leave":
        result = await sync_to_async(VoiceERPToolsService.reject_leave)(
            employee_name=args.get("employee_name", ""),
            reason=args.get("reason", "Administrative decision"),
            confirm=args.get("confirm", True),
            session_id=session_id,
        )
    elif tool_name == "confirm_action":
        result = await sync_to_async(VoiceERPToolsService.confirm_action)(session_id=session_id)
    elif tool_name == "get_top_customers":
        result = await sync_to_async(VoiceERPToolsService.get_top_customers)(session_id=session_id)
    elif tool_name == "get_pending_invoices":
        result = await sync_to_async(VoiceERPToolsService.get_pending_invoices)(
            month=args.get("month"),
            session_id=session_id,
        )
    elif tool_name == "get_low_stock_items":
        result = await sync_to_async(VoiceERPToolsService.get_low_stock_items)()
    elif tool_name == "get_overdue_invoices":
        result = await sync_to_async(VoiceERPToolsService.get_overdue_invoices)(session_id=session_id)
    elif tool_name == "get_pending_leaves":
        result = await sync_to_async(VoiceERPToolsService.get_pending_leaves)()
    elif tool_name == "plan_erp_replenishment":
        result = await sync_to_async(ERPPlannerAgent.plan_and_execute)(
            prompt=args.get("prompt", "Restock running low"),
            session_id=session_id,
        )
    else:
        return JSONResponse({"error": f"Unknown tool: {tool_name}"}, status_code=400)

    res_body = {
        "tool": tool_name,
        "speech": result.get("speech", ""),
        "data": result.get("data", result),
    }
    if "planner_mode" in result:
        res_body["planner_mode"] = result["planner_mode"]
    if "fallback_reason" in result:
        res_body["fallback_reason"] = result["fallback_reason"]
    return JSONResponse(res_body)


async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint providing server metadata and supported MCP version."""
    from django.db import connection

    def _check_db() -> bool:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return True
        except Exception:
            return False

    db_ok = await sync_to_async(_check_db)()

    return JSONResponse(
        {
            "status": "healthy",
            "server": SERVER_NAME,
            "version": SERVER_VERSION,
            "mcp_spec_version": MCP_SPEC_VERSION,
            "transport": "streamable_http",
            "mcp_endpoint": MCP_PATH,
            "database_connected": db_ok,
            "voice_assistant_target": "Alexa+",
            "web_chat_demo": "/chat",
            "aws_mock_mode": AWSConfig.is_mock_mode(),
            "planner_mode": "mock" if AWSConfig.is_mock_mode() else "bedrock",
        }
    )


async def root_info(request: Request):
    """Root info endpoint: serves web chat in browser or JSON metadata for API clients."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return await chat_page(request)

    return JSONResponse(
        {
            "name": "ERP Voice Agent",
            "description": "MCP server bridging Alexa+ to sample ERP (Invoices, Inventory, POs, HR Leave)",
            "mcp_spec_version": MCP_SPEC_VERSION,
            "streamable_http_url": f"{MCP_PATH}",
            "health_check_url": "/health",
            "web_chat_url": "/chat",
        }
    )


def create_app() -> Starlette:
    """Create and configure the Starlette application with MCP Streamable HTTP and web chat."""
    base_app: Starlette = mcp_server.streamable_http_app(streamable_http_path=MCP_PATH)

    # Register web chat & API helper routes
    base_app.add_route("/chat", chat_page, methods=["GET"])
    base_app.add_route("/api/chat", chat_api, methods=["POST"])
    base_app.add_route("/api/tool", tool_api, methods=["POST"])
    base_app.add_route("/health", health_check, methods=["GET"])
    base_app.add_route("/", root_info, methods=["GET"])

    # Wrap with protocol version middleware
    wrapped_app = MCPProtocolVersionMiddleware(base_app, protocol_version=MCP_SPEC_VERSION)
    return wrapped_app


app = create_app()

