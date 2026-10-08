"""django-erp-mcp: Reusable Model Context Protocol (MCP) adapter for Django applications."""

from django_erp_mcp.adapter import MCPModelAdapter
from django_erp_mcp.registry import DjangoMCPRegistry
from django_erp_mcp.decorators import mcp_model

__all__ = ["MCPModelAdapter", "DjangoMCPRegistry", "mcp_model"]
__version__ = "0.1.0"
