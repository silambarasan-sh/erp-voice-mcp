"""Runner script for launching the MCP Streamable HTTP server."""

import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

def main() -> None:
    """Run the Uvicorn server hosting the MCP Streamable HTTP application."""
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8000"))
    spec = os.getenv("MCP_PROTOCOL_VERSION", "2025-11-25")

    print("=" * 60)
    print("🚀 Starting ERP Voice Agent (MCP Streamable HTTP Server)")
    print(f"📡 Spec Version: {spec}")
    print(f"🌐 Host/Port:    http://{host}:{port}")
    print(f"🔌 MCP Endpoint: http://{host}:{port}/mcp")
    print(f"💓 Health Check: http://{host}:{port}/health")
    print("=" * 60)

    uvicorn.run("mcp_server.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
