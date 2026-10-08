"""ERP domain tools exposed to Amazon Bedrock and Strands Agent."""

from typing import Any, Dict, List, Optional
from erp_core.models import Supplier, Item
from erp_core.services import VoiceERPToolsService, PurchaseOrderService


def tool_get_low_stock_items() -> Dict[str, Any]:
    """Inspect inventory items currently at or below their reorder level."""
    return VoiceERPToolsService.get_low_stock_items()


def tool_get_suppliers() -> List[Dict[str, Any]]:
    """List all registered suppliers with their lead times in days and contact numbers."""
    return [s.to_dict() for s in Supplier.objects.all().order_by("lead_time_days")]


def tool_draft_purchase_order(
    item_skus: Optional[List[str]] = None,
    session_id: str = "default",
) -> Dict[str, Any]:
    """Create draft purchase orders for specified item SKUs grouped by supplier."""
    return VoiceERPToolsService.draft_purchase_order(
        item_skus=item_skus,
        session_id=session_id,
    )


def tool_list_purchase_orders(status: Optional[str] = None) -> Dict[str, Any]:
    """Query existing purchase orders by status."""
    return PurchaseOrderService.list_purchase_orders(status=status)
