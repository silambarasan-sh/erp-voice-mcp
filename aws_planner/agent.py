"""Amazon Bedrock ERP Planner Agent using Bedrock Converse Tool Use."""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from erp_core.models import Item, Supplier
from erp_core.services import VoiceERPToolsService, VoiceSessionService
from aws_planner.config import AWSConfig
from aws_planner.tools import BEDROCK_PLANNER_TOOL_SPECS, execute_planner_tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an ERP Supply Chain Planner Agent. You help users plan inventory replenishment. "
    "You have access to tools to inspect low stock items, check supplier lead times, and create draft purchase orders. "
    "Always use the available tools to inspect inventory and formulate replenishment orders. "
    "You can ONLY create DRAFT orders. You CANNOT and MUST NOT confirm orders or execute final approvals; "
    "confirmation is strictly reserved for the human operator. "
    "When you finish creating the draft, formulate a clear, concise spoken summary stating the draft ID and asking the user if they would like to confirm it."
)


class ERPPlannerAgent:
    """Multi-step ERP Planner Agent powered by Amazon Bedrock Converse Tool Use."""

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
        latency_ms: Optional[int] = None,
        bedrock_calls: int = 0,
    ) -> Dict[str, Any]:
        """Deterministic multi-step planning simulation matching Bedrock execution trace."""
        mock_start = time.time()
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

        effective_latency_ms = (
            latency_ms if latency_ms is not None else int((time.time() - mock_start) * 1000)
        )

        if not low_stock_items:
            speech = "All inventory items are currently well-stocked above reorder levels. No purchase orders are needed."
            data_payload = {
                "planner": planner_title,
                "model_id": AWSConfig.get_model_id(),
                "aws_region": AWSConfig.get_region(),
                "mock_mode": (planner_mode != "bedrock"),
                "planner_mode": planner_mode,
                "latency_ms": effective_latency_ms,
                "bedrock_calls": bedrock_calls,
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
                "latency_ms": effective_latency_ms,
                "bedrock_calls": bedrock_calls,
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
            "model_id": AWSConfig.get_model_id(),
            "aws_region": AWSConfig.get_region(),
            "mock_mode": (planner_mode != "bedrock"),
            "planner_mode": planner_mode,
            "latency_ms": effective_latency_ms,
            "bedrock_calls": bedrock_calls,
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
                "latency_ms": effective_latency_ms,
                "bedrock_calls": bedrock_calls,
                "data": data_payload,
            }
            if fallback_reason:
                res["fallback_reason"] = fallback_reason
            return res

        return {
            "speech": speech,
            "planner_mode": planner_mode,
            "latency_ms": effective_latency_ms,
            "bedrock_calls": bedrock_calls,
            "data": data_payload,
        }

    @classmethod
    def _plan_and_execute_bedrock(
        cls,
        prompt: str,
        session_id: str = "default",
    ) -> Dict[str, Any]:
        """Invoke Amazon Bedrock Foundation Model via Converse API tool-use loop."""
        start_time = time.time()
        bedrock_calls = 0

        try:
            client = AWSConfig.get_bedrock_runtime_client()
            if client is None:
                raise RuntimeError("Bedrock runtime client could not be initialized (client is None)")

            model_id = AWSConfig.get_model_id()
            messages: List[Dict[str, Any]] = [
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ]

            max_iterations = 5
            iteration = 0
            valid_tool_calls_made = 0
            plan_steps: List[str] = []
            executed_tool_traces: List[Dict[str, Any]] = []
            last_draft_details: Optional[Dict[str, Any]] = None
            model_final_speech = ""

            while iteration < max_iterations:
                iteration += 1
                bedrock_calls += 1
                call_start = time.time()

                response = client.converse(
                    modelId=model_id,
                    system=[{"text": SYSTEM_PROMPT}],
                    messages=messages,
                    toolConfig={"tools": BEDROCK_PLANNER_TOOL_SPECS},
                    inferenceConfig={"temperature": 0.2, "maxTokens": 1000},
                )
                call_latency_ms = int((time.time() - call_start) * 1000)
                stop_reason = response.get("stopReason", "end_turn")
                logger.info(
                    "Bedrock converse iteration %d completed in %d ms (stopReason: %s)",
                    iteration,
                    call_latency_ms,
                    stop_reason,
                )

                output_msg = response.get("output", {}).get("message", {})
                content_blocks = output_msg.get("content", [])
                messages.append({"role": "assistant", "content": content_blocks})

                # Check for assistant text (speech response candidate)
                text_parts = [b.get("text", "") for b in content_blocks if "text" in b]
                if text_parts:
                    model_final_speech = " ".join(text_parts).strip()

                # Extract tool use requests
                tool_use_blocks = [b.get("toolUse") for b in content_blocks if "toolUse" in b]

                if not tool_use_blocks or stop_reason == "end_turn":
                    break

                # Execute requested tools through ERP services and guardrails
                tool_results: List[Dict[str, Any]] = []
                for tool_use in tool_use_blocks:
                    tool_id = tool_use.get("toolUseId")
                    tool_name = tool_use.get("name")
                    tool_input = tool_use.get("input", {})

                    out_dict, step_str, draft_info = execute_planner_tool(
                        tool_name=tool_name,
                        tool_input=tool_input,
                        session_id=session_id,
                    )

                    if "error" not in out_dict:
                        valid_tool_calls_made += 1

                    if draft_info:
                        last_draft_details = draft_info

                    step_num = len(plan_steps) + 1
                    plan_steps.append(f"Step {step_num}: {step_str.replace('Step: ', '')}")
                    executed_tool_traces.append(
                        {
                            "tool": tool_name,
                            "arguments": tool_input,
                            "result": out_dict,
                        }
                    )

                    tool_results.append(
                        {
                            "toolResult": {
                                "toolUseId": tool_id,
                                "content": [{"json": out_dict}],
                                "status": "error" if "error" in out_dict else "success",
                            }
                        }
                    )

                messages.append({"role": "user", "content": tool_results})

                if stop_reason == "end_turn":
                    break

            total_latency_ms = int((time.time() - start_time) * 1000)

            # Guardrail requirement 4 & 5: Model must have made at least one valid tool call
            if valid_tool_calls_made == 0:
                logger.warning(
                    "Bedrock model completed without making valid tool calls. Falling back to local deterministic planner."
                )
                return cls._plan_and_execute_mock(
                    prompt=prompt,
                    session_id=session_id,
                    planner_mode="fallback",
                    fallback_reason="Bedrock model completed without making valid tool calls",
                    latency_ms=total_latency_ms,
                    bedrock_calls=bedrock_calls,
                )

            # Bedrock successfully planned with genuine tool use
            AWSConfig.set_last_live_call("ok")

            # Determine speech: model final message must include draft_id if draft was created
            draft_id = last_draft_details.get("draft_id") if last_draft_details else None
            cleaned_speech = re.sub(r"<thinking>.*?</thinking>", "", model_final_speech, flags=re.DOTALL).strip()

            if draft_id and (draft_id.lower() in cleaned_speech.lower()):
                final_speech = cleaned_speech
            elif last_draft_details:
                fastest_sup = last_draft_details.get("fastest_supplier")
                items_cnt = last_draft_details.get("items_count", 0)
                qty = last_draft_details.get("total_quantity", 0)
                suppliers = last_draft_details.get("suppliers", [])
                sup_str = ", ".join(suppliers[:2])
                if fastest_sup:
                    final_speech = (
                        f"I reviewed low stock items. {fastest_sup['name']} is the fastest supplier "
                        f"with a {fastest_sup['lead_time_days']}-day lead time. "
                        f"I drafted order {draft_id} for {items_cnt} items. Would you like me to confirm it?"
                    )
                else:
                    final_speech = (
                        f"I have created replenishment draft {draft_id} for {items_cnt} low stock items "
                        f"from {sup_str}. Total quantity is {qty}. Would you like me to confirm it?"
                    )
            elif cleaned_speech:
                final_speech = cleaned_speech
            else:
                final_speech = (
                    "All inventory items are currently well-stocked above reorder levels. No purchase orders are needed."
                )

            data_payload = {
                "planner": "Amazon Bedrock ERP Planner (AWS Builder Challenge)",
                "model_id": model_id,
                "aws_region": AWSConfig.get_region(),
                "mock_mode": False,
                "planner_mode": "bedrock",
                "latency_ms": total_latency_ms,
                "bedrock_calls": bedrock_calls,
                "prompt": prompt,
                "plan_steps": plan_steps,
                "tool_traces": executed_tool_traces,
                "draft_id": draft_id,
                "status": "draft" if last_draft_details else "none_needed",
                "requires_confirmation": bool(last_draft_details),
                "fastest_supplier": last_draft_details.get("fastest_supplier") if last_draft_details else None,
                "po_count": len(last_draft_details.get("po_ids", [])) if last_draft_details else 0,
                "po_ids": last_draft_details.get("po_ids", []) if last_draft_details else [],
                "suppliers": last_draft_details.get("suppliers", []) if last_draft_details else [],
                "items_count": last_draft_details.get("items_count", 0) if last_draft_details else 0,
                "total_quantity": last_draft_details.get("total_quantity", 0) if last_draft_details else 0,
                "items": last_draft_details.get("items", []) if last_draft_details else [],
            }

            return {
                "speech": final_speech,
                "planner_mode": "bedrock",
                "latency_ms": total_latency_ms,
                "bedrock_calls": bedrock_calls,
                "data": data_payload,
            }

        except Exception as exc:
            call_latency_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Amazon Bedrock call failed after %d ms (%s). Falling back to local deterministic planner.",
                call_latency_ms,
                exc,
            )
            AWSConfig.set_last_live_call("failed")
            error_reason = str(exc)
            return cls._plan_and_execute_mock(
                prompt=prompt,
                session_id=session_id,
                planner_mode="fallback",
                fallback_reason=error_reason,
                latency_ms=call_latency_ms,
                bedrock_calls=bedrock_calls,
            )
