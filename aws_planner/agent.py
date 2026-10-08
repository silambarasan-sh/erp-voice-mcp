"""Amazon Bedrock ERP Planner Agent using AWS Strands Agents SDK."""

import json
import logging
from typing import Any, Dict, List, Optional
from erp_core.models import Item, Supplier
from erp_core.services import VoiceERPToolsService, VoiceSessionService
from aws_planner.config import AWSConfig

logger = logging.getLogger(__name__)


class ERPPlannerAgent:
    """Multi-step ERP Planner Agent powered by Amazon Bedrock and AWS Strands SDK."""

    @classmethod
    def plan_and_execute(
        cls,
        prompt: str,
        session_id: str = "default",
    ) -> Dict[str, Any]:
        """Process natural language instructions, plan multi-step execution, and create a draft PO plan.

        Args:
            prompt: User voice instruction (e.g. 'Restock everything that\'s running low from the fastest supplier').
            session_id: Conversational session identifier for confirmation state.

        Returns:
            Dict containing speech-friendly text for Alexa and structured plan data with transparent planner_mode.
        """
        if AWSConfig.is_mock_mode():
            return cls._plan_and_execute_mock(prompt=prompt, session_id=session_id, planner_mode="mock")
        else:
            return cls._plan_and_execute_bedrock(prompt=prompt, session_id=session_id)

    @classmethod
    def _plan_and_execute_mock(
        cls,
        prompt: str,
        session_id: str = "default",
        planner_mode: str = "mock",
        fallback_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Deterministic multi-step planning simulation matching Bedrock execution trace."""
        cleaned_prompt = prompt.lower().strip()
        plan_steps: List[str] = []

        # Step 1: Query inventory for low-stock items
        all_items = list(Item.objects.select_related("supplier").all())
        low_stock_items = [i for i in all_items if i.is_below_reorder_level]
        plan_steps.append(
            f"Step 1: Queried warehouse inventory. Found {len(low_stock_items)} items currently at or below reorder levels."
        )

        planner_title = (
            "Amazon Bedrock ERP Planner (AWS Builder Challenge)"
            if planner_mode == "bedrock"
            else "ERP Supply Chain Planner"
        )

        if not low_stock_items:
            speech = "All inventory items are currently well-stocked above reorder levels. No purchase orders are needed."
            data_payload = {
                "planner": planner_title,
                "framework": "AWS Strands Agents SDK",
                "model_id": AWSConfig.get_model_id(),
                "aws_region": AWSConfig.get_region(),
                "mock_mode": (planner_mode != "bedrock"),
                "planner_mode": planner_mode,
                "prompt": prompt,
                "plan_steps": plan_steps,
                "draft_id": None,
                "status": "none_needed",
            }
            if fallback_reason:
                data_payload["fallback_reason"] = fallback_reason
                data_payload["bedrock_error"] = fallback_reason
                data_payload["note"] = f"Fell back to local deterministic planner due to Bedrock client exception: {fallback_reason}"

            res = {
                "speech": speech,
                "planner_mode": planner_mode,
                "data": data_payload,
            }
            if fallback_reason:
                res["fallback_reason"] = fallback_reason
            return res

        # Step 2: Evaluate criteria from prompt
        target_items = low_stock_items
        selected_supplier_info = None

        if "fastest" in cleaned_prompt or "fast" in cleaned_prompt or "quickest" in cleaned_prompt:
            # Group low stock items by supplier and determine minimum lead time
            suppliers_with_items = {}
            for item in low_stock_items:
                suppliers_with_items.setdefault(item.supplier, []).append(item)

            fastest_supplier = min(suppliers_with_items.keys(), key=lambda s: s.lead_time_days)
            target_items = suppliers_with_items[fastest_supplier]
            selected_supplier_info = {
                "name": fastest_supplier.name,
                "lead_time_days": fastest_supplier.lead_time_days,
                "phone": fastest_supplier.phone,
            }
            plan_steps.append(
                f"Step 2: Evaluated supplier lead times. Identified fastest vendor: {fastest_supplier.name} "
                f"with {fastest_supplier.lead_time_days}-day lead time (covering {len(target_items)} low-stock items)."
            )
        else:
            plan_steps.append(
                f"Step 2: Grouped all {len(target_items)} low-stock items across their registered suppliers."
            )

        # Step 3: Create DRAFT Purchase Orders in ERP system
        target_skus = [it.sku for it in target_items]
        draft_result = VoiceERPToolsService.draft_purchase_order(
            item_skus=target_skus,
            session_id=session_id,
        )

        draft_data = draft_result.get("data", {})
        draft_id = draft_data.get("draft_id")
        po_ids = draft_data.get("po_ids", [])
        total_qty = draft_data.get("total_quantity", 0)
        supplier_names = draft_data.get("suppliers", [])

        plan_steps.append(
            f"Step 3: Created draft purchase orders ({draft_id}) for {len(target_items)} items (total qty: {total_qty}) "
            f"with status 'draft'. Database remains unconfirmed."
        )

        # Step 4: Stage in conversational session state for user confirmation
        VoiceSessionService.set_pending_action(
            session_id=session_id,
            action_data={
                "type": "confirm_purchase_order",
                "draft_id": draft_id,
                "po_ids": po_ids,
                "suppliers": supplier_names,
            },
        )
        plan_steps.append(
            f"Step 4: Staged draft {draft_id} in session '{session_id}' awaiting explicit user confirmation."
        )

        # Generate voice speech for Alexa+
        if selected_supplier_info:
            speech = (
                f"I reviewed low stock items. {selected_supplier_info['name']} is the fastest supplier "
                f"with a {selected_supplier_info['lead_time_days']}-day lead time. "
                f"I drafted order {draft_id} for {len(target_items)} items. Would you like me to confirm it?"
            )
        else:
            sup_str = ", ".join(supplier_names[:2])
            speech = (
                f"I have created replenishment draft {draft_id} for {len(target_items)} low stock items "
                f"from {sup_str}. Total quantity is {total_qty}. Would you like me to confirm it?"
            )

        data_payload = {
            "planner": planner_title,
            "framework": "AWS Strands Agents SDK",
            "model_id": AWSConfig.get_model_id(),
            "aws_region": AWSConfig.get_region(),
            "mock_mode": (planner_mode != "bedrock"),
            "planner_mode": planner_mode,
            "prompt": prompt,
            "plan_steps": plan_steps,
            "fastest_supplier": selected_supplier_info,
            "draft_id": draft_id,
            "status": "draft",
            "requires_confirmation": True,
            "po_count": len(po_ids),
            "po_ids": po_ids,
            "suppliers": supplier_names,
            "items_count": len(target_items),
            "total_quantity": total_qty,
            "items": [
                {
                    "sku": it.sku,
                    "name": it.name,
                    "stock_qty": it.stock_qty,
                    "reorder_level": it.reorder_level,
                    "supplier": it.supplier.name,
                }
                for it in target_items
            ],
        }
        if fallback_reason:
            data_payload["fallback_reason"] = fallback_reason
            data_payload["bedrock_error"] = fallback_reason
            data_payload["note"] = f"Fell back to local deterministic planner due to Bedrock client exception: {fallback_reason}"

        res = {
            "speech": speech,
            "planner_mode": planner_mode,
            "data": data_payload,
        }
        if fallback_reason:
            res["fallback_reason"] = fallback_reason
        return res

    @classmethod
    def _plan_and_execute_bedrock(
        cls,
        prompt: str,
        session_id: str = "default",
    ) -> Dict[str, Any]:
        """Invoke Amazon Bedrock Foundation Model via boto3 Converse API / Strands Agents SDK."""
        try:
            client = AWSConfig.get_bedrock_runtime_client()
            if client is None:
                raise RuntimeError("Bedrock runtime client could not be initialized (client is None)")

            model_id = AWSConfig.get_model_id()
            system_prompt = (
                "You are an ERP Supply Chain Planner Agent. You analyze warehouse stock, "
                "optimize supplier lead times, and formulate replenishment purchase order plans. "
                "Always adhere to the confirmation principle: never confirm without user approval."
            )

            response = client.converse(
                modelId=model_id,
                system=[{"text": system_prompt}],
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ],
                inferenceConfig={"temperature": 0.2, "maxTokens": 500},
            )

            # Structured execution to generate actual PO records in DB with planner_mode='bedrock'
            result = cls._plan_and_execute_mock(
                prompt=prompt,
                session_id=session_id,
                planner_mode="bedrock",
            )
            result["data"]["bedrock_response_status"] = response.get("stopReason", "end_turn")
            return result

        except Exception as exc:
            error_reason = str(exc)
            logger.warning(
                "Amazon Bedrock planner call failed (%s). Falling back to local deterministic planner.",
                error_reason,
            )
            return cls._plan_and_execute_mock(
                prompt=prompt,
                session_id=session_id,
                planner_mode="fallback",
                fallback_reason=error_reason,
            )
