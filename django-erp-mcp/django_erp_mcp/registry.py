"""Registry connecting Django Model Adapters to Model Context Protocol (MCP) servers."""

from typing import Any, Callable, Dict, List, Optional, Type
from django.db import models
from asgiref.sync import sync_to_async
from django_erp_mcp.adapter import MCPModelAdapter


class DjangoMCPRegistry:
    """Registry that registers Django model query and action tools onto an MCP server."""

    def __init__(self, mcp_server: Any) -> None:
        """Initialize with an MCP Server instance (e.g. mcp.server.mcpserver.MCPServer)."""
        self.mcp_server = mcp_server
        self.adapters: Dict[str, MCPModelAdapter] = {}

    def register_model(
        self,
        model: Type[models.Model],
        read_fields: Optional[List[str]] = None,
        search_fields: Optional[List[str]] = None,
        voice_formatter: Optional[Callable[[List[Any]], str]] = None,
        adapter_class: Type[MCPModelAdapter] = MCPModelAdapter,
        **kwargs: Any,
    ) -> MCPModelAdapter:
        """Register a Django model, automatically binding query tools onto the MCP server."""
        adapter = adapter_class(
            model=model,
            read_fields=read_fields,
            search_fields=search_fields,
            voice_formatter=voice_formatter,
            **kwargs,
        )
        model_name = adapter.model_name
        self.adapters[model_name] = adapter

        # Dynamically register query tool on MCP server
        query_tool_name = f"query_{model_name}"
        get_tool_name = f"get_{model_name}"

        async def _query_tool(
            search: Optional[str] = None,
            limit: int = 10,
        ) -> Dict[str, Any]:
            return await sync_to_async(adapter.query_records)(search=search, limit=limit)

        async def _get_tool(record_id: int) -> Dict[str, Any]:
            return await sync_to_async(adapter.get_record)(record_id=record_id)

        # Set docstrings for AI/voice discovery
        _query_tool.__name__ = query_tool_name
        _query_tool.__doc__ = f"Search and query {model._meta.verbose_name_plural} with speech-friendly voice summary."

        _get_tool.__name__ = get_tool_name
        _get_tool.__doc__ = f"Retrieve details for a specific {model._meta.verbose_name} by ID."

        self.mcp_server.tool()(_query_tool)
        self.mcp_server.tool()(_get_tool)

        return adapter

    def get_adapter(self, model_name: str) -> Optional[MCPModelAdapter]:
        """Retrieve registered adapter by model name."""
        return self.adapters.get(model_name.lower())
