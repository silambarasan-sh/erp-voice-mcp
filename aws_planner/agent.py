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
    "When instructed to restock running low items from the fastest supplier: "
    "1. Call get_low_stock_items to inspect warehouse inventory at or below reorder levels. "
    "2. Call get_supplier_lead_times to evaluate supplier lead times. "
    "3. Identify which suppliers provide the low-stock items, and pick the single supplier with the SHORTEST lead time among those low-stock suppliers. "
    "4. Call draft_purchase_order exactly ONCE containing all low-stock item SKUs for that chosen fastest supplier. You must NEVER mix SKUs from multiple suppliers in a single draft call, and you must NOT call draft_purchase_order a second time. "
    "5. Formulate your final response in plain text: exactly 2 sentences, strictly under 45 words, no markdown, no asterisks, no lists. State the draft ID, supplier name, lead time, item count, and mention how many other low-stock items remain from slower suppliers. "
    "Safety invariant: You can ONLY create DRAFT orders. You CANNOT confirm orders or approve leaves; confirmation is strictly a human step."
)


def build_voice_speech(
    model_text: str,
    draft_id: Optional[str],
    supplier_name: Optional[str],
    lead_time_days: Optional[int],
    item_count: int,
    other_low_count: int,
) -> str:
    """Produce plain text voice speech adhering to: 2 sentences, under 45 words, no markdown, no asterisks, no lists."""
    if not draft_id or not supplier_name:
        return "All inventory items are currently well-stocked above reorder levels. No purchase orders are needed."

    # Build reliable deterministic template speech from real tool results
    other_phrase = (
        f"{other_low_count} other {'item remains' if other_low_count == 1 else 'items remain'} low from slower suppliers"
        if other_low_count > 0
        else "All other items are well-stocked"
    )
    fallback_speech = (
        f"I created draft {draft_id} for {item_count} items from {supplier_name} with a {lead_time_days}-day lead time. "
        f"{other_phrase}; would you like to confirm?"
    )

    if not model_text:
        return fallback_speech

    # Remove thinking tags
    clean_text = re.sub(r"<thinking>.*?</thinking>", "", model_text, flags=re.DOTALL).strip()

    # Reject if original text has markdown indicators (asterisks, bullet points, headers, numbered lists)
    has_markdown = bool(re.search(r"[*#_`\[\]]|\n\s*[-+*•]|\n\s*\d+\.", clean_text))
    if has_markdown:
        return fallback_speech

    # Clean whitespace and strip any stray markdown characters
    clean_text = re.sub(r"[*#_`\[\]]", "", clean_text)
    clean_text = " ".join(clean_text.split()).strip()

    # Validate draft_id is present
    if draft_id.lower() not in clean_text.lower():
        return fallback_speech

    # Validate word count (strictly under 45 words)
    words = clean_text.split()
    if len(words) >= 45:
        return fallback_speech

    # Validate exactly 2 sentences
    sentence_endings = [m.start() for m in re.finditer(r"[.!?](?:\s|$)", clean_text)]
    if len(sentence_endings) != 2:
        return fallback_speech

    return clean_text


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

        # Reset draft creation tracker for this session request
        session = VoiceSessionService.get_session(session_id)
        session["planner_draft_created"] = False

        # Step 1: Query inventory for low-stock items
        all_items = list(Item.objects.select_related("supplier").all())
        low_stock_items = [i for i in all_items if i.is_below_reorder_level]
        plan_steps.append(
            f"Step 1: Queried warehouse inventory. Found {len(low_stock_items)} items currently at or below reorder levels."
        )

        planner_title = "Amazon Bedrock ERP Planner"

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

        # Generate voice speech (strictly 2 sentences, under 45 words, plain text)
        other_low_count = max(0, len(low_stock_items) - len(target_items))
        if selected_supplier_info:
            speech = build_voice_speech(
                model_text="",
                draft_id=draft_id,
                supplier_name=selected_supplier_info["name"],
                lead_time_days=selected_supplier_info["lead_time_days"],
                item_count=len(target_items),
                other_low_count=other_low_count,
            )
        else:
            sup_str = ", ".join(supplier_names[:2])
            speech = (
                f"I created replenishment draft {draft_id} for {len(target_items)} items from {sup_str}. "
                f"Total quantity is {total_qty}; would you like me to confirm?"
            )

        mock_tool_traces = [
            {
                "tool": "get_low_stock_items",
                "arguments": {},
                "result": {"count": len(low_stock_items), "items": [it.sku for it in low_stock_items]},
            },
            {
                "tool": "get_supplier_lead_times",
                "arguments": {},
                "result": {"suppliers": [{"name": s.name, "lead_time_days": s.lead_time_days} for s in Supplier.objects.all()]},
            },
            {
                "tool": "draft_purchase_order",
                "arguments": {"item_skus": target_skus},
                "result": {
                    "draft_id": draft_id,
                    "items_count": len(target_items),
                    "total_quantity": total_qty,
                    "suppliers": supplier_names,
                },
            },
        ]

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
            "tool_traces": mock_tool_traces,
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
                "tool_traces": mock_tool_traces,
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
            "tool_traces": mock_tool_traces,
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

        # Reset draft creation tracker for this session request
        session = VoiceSessionService.get_session(session_id)
        session["planner_draft_created"] = False

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

            # Guardrail: Model must have made at least one valid tool call
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

            # Calculate total low-stock items in DB to compute remaining items accurately
            all_low_items = [i for i in Item.objects.select_related("supplier").all() if i.is_below_reorder_level]
            total_low_stock_count = len(all_low_items)

            draft_id = last_draft_details.get("draft_id") if last_draft_details else None
            fastest_sup = last_draft_details.get("fastest_supplier") if last_draft_details else None
            items_in_draft = last_draft_details.get("items_count", 0) if last_draft_details else 0
            other_low_count = max(0, total_low_stock_count - items_in_draft)

            # Build concise 2-sentence plain text voice speech (< 45 words, no markdown)
            final_speech = build_voice_speech(
                model_text=model_final_speech,
                draft_id=draft_id,
                supplier_name=fastest_sup["name"] if fastest_sup else None,
                lead_time_days=fastest_sup["lead_time_days"] if fastest_sup else None,
                item_count=items_in_draft,
                other_low_count=other_low_count,
            )

            data_payload = {
                "planner": "Amazon Bedrock ERP Planner",
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
                "fastest_supplier": fastest_sup,
                "po_count": len(last_draft_details.get("po_ids", [])) if last_draft_details else 0,
                "po_ids": last_draft_details.get("po_ids", []) if last_draft_details else [],
                "suppliers": last_draft_details.get("suppliers", []) if last_draft_details else [],
                "items_count": items_in_draft,
                "total_quantity": last_draft_details.get("total_quantity", 0) if last_draft_details else 0,
                "items": last_draft_details.get("items", []) if last_draft_details else [],
            }

            return {
                "speech": final_speech,
                "planner_mode": "bedrock",
                "latency_ms": total_latency_ms,
                "bedrock_calls": bedrock_calls,
                "tool_traces": executed_tool_traces,
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
