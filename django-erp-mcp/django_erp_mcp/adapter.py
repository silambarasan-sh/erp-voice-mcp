"""Core adapter translating Django models into Model Context Protocol (MCP) tool endpoints."""

from typing import Any, Callable, Dict, List, Optional, Type
from django.db import models
from django.db.models import Q
from asgiref.sync import sync_to_async


class MCPModelAdapter:
    """Configurable adapter exposing a Django Model as speech-ready MCP tools."""

    model: Type[models.Model]
    read_fields: Optional[List[str]] = None
    search_fields: Optional[List[str]] = None
    voice_formatter: Optional[Callable[[Any], str]] = None
    require_confirmation: bool = True

    def __init__(
        self,
        model: Type[models.Model],
        read_fields: Optional[List[str]] = None,
        search_fields: Optional[List[str]] = None,
        voice_formatter: Optional[Callable[[Any], str]] = None,
        require_confirmation: bool = True,
    ) -> None:
        self.model = model
        self.read_fields = read_fields
        self.search_fields = search_fields or []
        self.voice_formatter = voice_formatter
        self.require_confirmation = require_confirmation

    @property
    def model_name(self) -> str:
        """Return lower-cased model name."""
        return self.model._meta.model_name

    def serialize_instance(self, instance: models.Model) -> Dict[str, Any]:
        """Convert model instance to a dictionary according to read_fields."""
        if hasattr(instance, "to_dict") and callable(instance.to_dict):
            data = instance.to_dict()
        else:
            data = {}
            for field in instance._meta.fields:
                if self.read_fields is None or field.name in self.read_fields:
                    val = getattr(instance, field.name)
                    # Convert dates and decimals to serializable types
                    if hasattr(val, "isoformat"):
                        val = val.isoformat()
                    elif hasattr(val, "__float__"):
                        val = float(val)
                    data[field.name] = val
        return data

    def query_records(
        self,
        search: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Query instances, compute speech summary, and return structured payload."""
        qs = self.model.objects.all()

        if filters:
            qs = qs.filter(**filters)

        if search and self.search_fields:
            query = Q()
            for field in self.search_fields:
                query |= Q(**{f"{field}__icontains": search})
            qs = qs.filter(query)

        instances = list(qs[:limit])
        count = qs.count()

        serialized = [self.serialize_instance(inst) for inst in instances]

        # Generate voice summary
        if self.voice_formatter:
            speech = self.voice_formatter(instances)
        else:
            verbose_name = self.model._meta.verbose_name_plural
            if count == 0:
                speech = f"No {verbose_name} found matching your query."
            elif count == 1:
                speech = f"Found 1 {self.model._meta.verbose_name}."
            else:
                speech = f"Found {count} {verbose_name}. Showing the first {len(instances)}."

        return {
            "speech": speech,
            "data": {
                "count": count,
                "model": self.model_name,
                "records": serialized,
            },
        }

    def get_record(self, record_id: Any) -> Dict[str, Any]:
        """Fetch a single record by primary key."""
        try:
            inst = self.model.objects.get(pk=record_id)
            serialized = self.serialize_instance(inst)
            speech = f"Found {self.model._meta.verbose_name} #{record_id}."
            return {
                "speech": speech,
                "data": {"found": True, "record": serialized},
            }
        except self.model.DoesNotExist:
            return {
                "speech": f"{self.model._meta.verbose_name} #{record_id} does not exist.",
                "data": {"found": False, "error": f"Record {record_id} not found"},
            }
