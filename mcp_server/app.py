import os
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
        }
    )


async def root_info(request: Request) -> JSONResponse:
    """Root info endpoint directing clients to the MCP Streamable HTTP endpoint."""
    return JSONResponse(
        {
            "name": "ERP Voice Agent",
            "description": "MCP server bridging Alexa+ to sample ERP (Invoices, Inventory, POs, HR Leave)",
            "mcp_spec_version": MCP_SPEC_VERSION,
            "streamable_http_url": f"{MCP_PATH}",
            "health_check_url": "/health",
        }
    )


def create_app() -> Starlette:
    """Create and configure the Starlette application with MCP Streamable HTTP."""
    base_app: Starlette = mcp_server.streamable_http_app(streamable_http_path=MCP_PATH)

    # Register additional helper routes
    base_app.add_route("/health", health_check, methods=["GET"])
    base_app.add_route("/", root_info, methods=["GET"])

    # Wrap with protocol version middleware
    wrapped_app = MCPProtocolVersionMiddleware(base_app, protocol_version=MCP_SPEC_VERSION)
    return wrapped_app


app = create_app()
