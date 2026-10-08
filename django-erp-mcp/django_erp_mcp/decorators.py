"""Decorators for registering Django models and action methods as MCP tools."""

from typing import Any, Callable, List, Optional, Type
from django.db import models


def mcp_model(
    registry: Any,
    read_fields: Optional[List[str]] = None,
    search_fields: Optional[List[str]] = None,
    voice_formatter: Optional[Callable[[List[Any]], str]] = None,
    **kwargs: Any,
) -> Callable[[Type[models.Model]], Type[models.Model]]:
    """Class decorator registering a Django model directly with an MCP Registry.

    Example:
        @mcp_model(
            registry=my_mcp_registry,
            search_fields=["name", "city"],
            voice_formatter=lambda items: f"Found {len(items)} customers."
        )
        class Customer(models.Model):
            ...
    """
    def decorator(cls: Type[models.Model]) -> Type[models.Model]:
        registry.register_model(
            model=cls,
            read_fields=read_fields,
            search_fields=search_fields,
            voice_formatter=voice_formatter,
            **kwargs,
        )
        return cls

    return decorator
