"""Amazon Bedrock Converse tool definitions and execution guardrails."""

import logging
from typing import Any, Dict, List, Optional, Tuple
from django.db import transaction
from erp_core.models import Item, PurchaseOrder, PurchaseOrderLine, Supplier
from erp_core.services import VoiceSessionService

logger = logging.getLogger(__name__)

# Maximum order quantity allowed per line item to prevent unbounded ordering
MAX_QTY_PER_ITEM = 100

# Exactly and ONLY the allowed tools exposed to the Bedrock Converse toolConfig
ALLOWED_TOOLS = {"get_low_stock_items", "get_supplier_lead_times", "draft_purchase_order"}

BEDROCK_PLANNER_TOOL_SPECS = [
    {
        "toolSpec": {
            "name": "get_low_stock_items",
            "description": (
                "Inspect warehouse inventory to identify all items currently at or below their reorder level. "
                "Returns item SKU, name, current stock, reorder level, and supplier information."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_supplier_lead_times",
            "description": (
                "List all registered suppliers ordered by lead time (in days). "
                "Use this to find the fastest supplier for restocking."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "draft_purchase_order",
            "description": (
                "Create a DRAFT replenishment purchase order for the specified item SKUs. "
                "This strictly creates draft orders awaiting human confirmation. Does NOT confirm or place orders."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "item_skus": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of item SKUs to restock from the supplier",
                        }
                    },
                    "required": ["item_skus"],
                }
            },
        }
    },
]


def execute_low_stock_items() -> Tuple[Dict[str, Any], str]:
    """Inspect inventory items currently at or below their reorder level."""
    all_items = list(Item.objects.select_related("supplier").all())
    low_stock = [i for i in all_items if i.is_below_reorder_level]
    items_data = [
        {
            "sku": it.sku,
            "name": it.name,
            "stock_qty": it.stock_qty,
            "reorder_level": it.reorder_level,
            "supplier_id": it.supplier.id,
            "supplier_name": it.supplier.name,
            "lead_time_days": it.supplier.lead_time_days,
        }
        for it in low_stock
    ]
    return (
        {"items": items_data, "count": len(items_data)},
        f"Step: Called get_low_stock_items(). Found {len(items_data)} items at or below reorder levels.",
    )


def execute_supplier_lead_times() -> Tuple[Dict[str, Any], str]:
    """List all registered suppliers ordered by lead time."""
    suppliers = list(Supplier.objects.all().order_by("lead_time_days"))
    sup_data = [
        {
            "id": s.id,
            "name": s.name,
            "lead_time_days": s.lead_time_days,
            "phone": s.phone,
        }
        for s in suppliers
    ]
    fastest_desc = f"{suppliers[0].name} ({suppliers[0].lead_time_days} days)" if suppliers else "none"
    return (
        {"suppliers": sup_data, "count": len(sup_data)},
        f"Step: Called get_supplier_lead_times(). Evaluated {len(sup_data)} suppliers (fastest: {fastest_desc}).",
    )


def execute_draft_purchase_order(
    item_skus: Any,
    session_id: str = "default",
) -> Tuple[Dict[str, Any], str, Optional[Dict[str, Any]]]:
    """Draft purchase orders with strict Python validation and guardrails.

    Guardrails:
    1. Validates that item_skus is a non-empty list of strings.
    2. Validates that every requested SKU exists in the inventory database.
    3. Allows only DRAFT status creation.
    4. Caps order quantity per item line (MAX_QTY_PER_ITEM).
    5. Stages the draft order in the session state for human confirmation.
    """
    if not isinstance(item_skus, list) or not item_skus:
        return (
            {"error": "Invalid argument: 'item_skus' must be a non-empty list of string SKUs."},
            "Step: Refused draft_purchase_order (item_skus was empty or invalid).",
            None,
        )

    # 1. Validate all SKUs exist in database
    existing_items = list(Item.objects.filter(sku__in=item_skus).select_related("supplier"))
    existing_skus = {it.sku for it in existing_items}
    missing_skus = [sku for sku in item_skus if sku not in existing_skus]
    if missing_skus:
        return (
            {
                "error": f"Invalid SKU(s): {missing_skus}. All items must exist in inventory.",
                "valid_skus_found": list(existing_skus),
            },
            f"Step: Refused draft_purchase_order for non-existent SKUs: {missing_skus}.",
            None,
        )

    # Group items by supplier
    supplier_map: Dict[Any, List[Item]] = {}
    for item in existing_items:
        supplier_map.setdefault(item.supplier, []).append(item)

    created_pos: List[PurchaseOrder] = []
    total_qty = 0

    with transaction.atomic():
        for supplier, sup_items in supplier_map.items():
            # Strict Guardrail: Always create with status='draft'
            po = PurchaseOrder.objects.create(supplier=supplier, status="draft")
            for it in sup_items:
                calc_qty = max(it.reorder_level * 2 - it.stock_qty, it.reorder_level, 10)
                # Strict Guardrail: Cap order quantity per line item
                capped_qty = min(calc_qty, MAX_QTY_PER_ITEM)
                PurchaseOrderLine.objects.create(po=po, item=it, qty=capped_qty)
                total_qty += capped_qty
            created_pos.append(po)

    primary_id = created_pos[0].id
    draft_id = f"DRAFT-PO-{primary_id}"
    po_ids = [p.id for p in created_pos]
    supplier_names = [s.name for s in supplier_map.keys()]

    # Strict Guardrail: Stage draft in session exactly as required for confirmation
    session = VoiceSessionService.get_session(session_id)
    session["last_draft_id"] = draft_id
    session["last_draft_po_ids"] = po_ids
    VoiceSessionService.set_context(
        session_id=session_id,
        context_type="draft_purchase_order",
        data={
            "draft_id": draft_id,
            "po_ids": po_ids,
            "suppliers": supplier_names,
        },
    )
    VoiceSessionService.set_pending_action(
        session_id=session_id,
        action_data={
            "type": "confirm_purchase_order",
            "draft_id": draft_id,
            "po_ids": po_ids,
            "suppliers": supplier_names,
        },
    )

    fastest_supplier = min(supplier_map.keys(), key=lambda s: s.lead_time_days)
    draft_details = {
        "draft_id": draft_id,
        "po_ids": po_ids,
        "suppliers": supplier_names,
        "fastest_supplier": {
            "name": fastest_supplier.name,
            "lead_time_days": fastest_supplier.lead_time_days,
            "phone": fastest_supplier.phone,
        },
        "items_count": len(existing_items),
        "total_quantity": total_qty,
        "items": [
            {
                "sku": it.sku,
                "name": it.name,
                "stock_qty": it.stock_qty,
                "reorder_level": it.reorder_level,
                "supplier": it.supplier.name,
            }
            for it in existing_items
        ],
    }

    step_text = (
        f"Step: Called draft_purchase_order(item_skus={item_skus}). "
        f"Created draft {draft_id} for {len(existing_items)} items from {', '.join(supplier_names)} "
        f"(Total Qty: {total_qty}). Staged in session for user confirmation."
    )

    return (
        {
            "success": True,
            "draft_id": draft_id,
            "po_ids": po_ids,
            "status": "draft",
            "items_count": len(existing_items),
            "total_quantity": total_qty,
            "suppliers": supplier_names,
        },
        step_text,
        draft_details,
    )


def execute_planner_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    session_id: str = "default",
) -> Tuple[Dict[str, Any], str, Optional[Dict[str, Any]]]:
    """Dispatcher enforcing tool allowlisting and guardrails."""
    # Strict Guardrail: refuse any confirm or unauthorized tool
    if tool_name not in ALLOWED_TOOLS:
        is_confirm = "confirm" in tool_name or "approve" in tool_name or "reject" in tool_name
        msg = (
            f"Tool '{tool_name}' is unauthorized. Confirmation and approval actions require explicit "
            f"human review and cannot be executed autonomously."
            if is_confirm
            else f"Tool '{tool_name}' is not recognized. Allowed tools are: {list(ALLOWED_TOOLS)}."
        )
        return (
            {"error": msg, "tool": tool_name},
            f"Step: Guardrail refused execution of unauthorized tool '{tool_name}'.",
            None,
        )

    if tool_name == "get_low_stock_items":
        result, step = execute_low_stock_items()
        return result, step, None

    elif tool_name == "get_supplier_lead_times":
        result, step = execute_supplier_lead_times()
        return result, step, None

    elif tool_name == "draft_purchase_order":
        item_skus = tool_input.get("item_skus")
        return execute_draft_purchase_order(item_skus=item_skus, session_id=session_id)

    return ({"error": f"Unhandled tool: {tool_name}"}, f"Step: Unhandled tool '{tool_name}'.", None)
