"""Tests for the Amazon Bedrock ERP Planner Agent using Bedrock Converse Tool Use."""

import pytest
from erp_core.models import PurchaseOrder, Item
from erp_core.services import VoiceSessionService
from aws_planner.config import AWSConfig
from aws_planner.agent import ERPPlannerAgent
from mcp_server.server import plan_erp_replenishment, confirm_action


@pytest.fixture(autouse=True)
def reset_voice_sessions():
    """Ensure clean session state before and after each test."""
    VoiceSessionService.reset()
    AWSConfig.set_last_live_call("not_called_yet")
    yield
    VoiceSessionService.reset()
    AWSConfig.set_last_live_call("not_called_yet")


def test_aws_config_defaults_and_env():
    """Verify AWS region, model ID, mock mode, and last live call configuration."""
    assert AWSConfig.get_region() is not None
    assert "amazon" in AWSConfig.get_model_id().lower() or "claude" in AWSConfig.get_model_id().lower()
    assert AWSConfig.is_mock_mode() is True  # Default for testing/demo
    assert AWSConfig.get_last_live_call() == "not_called_yet"


@pytest.mark.django_db(transaction=True)
def test_plan_fastest_supplier_replenishment():
    """Verify agent plans multiple steps, selects fastest supplier, and creates draft PO."""
    session_id = "test_planner_fastest_session"
    prompt = "Restock everything that's running low from the fastest supplier"

    result = ERPPlannerAgent.plan_and_execute(prompt=prompt, session_id=session_id)

    assert "speech" in result
    assert "data" in result
    assert result["planner_mode"] == "mock"
    assert result["data"]["planner_mode"] == "mock"
    data = result["data"]

    # Verify multi-step plan steps are documented
    assert "plan_steps" in data
    assert len(data["plan_steps"]) >= 3
    assert any("queried" in step.lower() for step in data["plan_steps"])
    assert any("fastest" in step.lower() or "lead time" in step.lower() for step in data["plan_steps"])
    assert any("draft" in step.lower() for step in data["plan_steps"])

    # Verify fastest supplier was selected
    assert data["fastest_supplier"] is not None
    assert "name" in data["fastest_supplier"]
    assert "lead_time_days" in data["fastest_supplier"]

    # Verify DRAFT PO was created in DB and remains in 'draft' status
    draft_id = data["draft_id"]
    assert draft_id.startswith("DRAFT-PO-")
    assert data["status"] == "draft"
    assert data["requires_confirmation"] is True
    assert "latency_ms" in result
    assert "bedrock_calls" in result
    assert result["bedrock_calls"] == 0
    assert result["data"]["bedrock_calls"] == 0
    assert result["data"]["latency_ms"] >= 0

    for po_id in data["po_ids"]:
        po = PurchaseOrder.objects.get(id=po_id)
        assert po.status == "draft"

    # Verify speech asks for confirmation
    assert "confirm" in result["speech"].lower()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_planner_then_confirm_it_workflow():
    """Verify end-to-end flow: Bedrock planner drafts PO -> user says 'confirm it' -> PO confirmed."""
    session_id = "test_bedrock_confirm_flow"
    prompt = "Restock everything that's running low from the fastest supplier"

    # Step 1: Agent creates plan and draft PO
    plan_res = await plan_erp_replenishment(prompt=prompt, session_id=session_id)
    po_ids = plan_res["data"]["po_ids"]
    assert len(po_ids) > 0

    # Verify all POs are still draft
    for po_id in po_ids:
        po = await PurchaseOrder.objects.aget(id=po_id)
        assert po.status == "draft"

    # Step 2: User says "confirm it" -> confirms via session state
    confirm_res = await confirm_action(session_id=session_id)
    assert confirm_res["data"]["success"] is True
    assert confirm_res["data"]["status"] == "confirmed"

    # Verify POs are now confirmed in DB
    for po_id in po_ids:
        po = await PurchaseOrder.objects.aget(id=po_id)
        assert po.status == "confirmed"


@pytest.mark.django_db(transaction=True)
def test_planner_when_no_low_stock_needed():
    """Verify agent politely informs when inventory levels are already sufficient."""
    # Temporarily set all items above reorder level
    Item.objects.all().update(stock_qty=1000, reorder_level=10)

    prompt = "Restock everything that's running low"
    result = ERPPlannerAgent.plan_and_execute(prompt=prompt, session_id="test_no_low_stock")

    assert "well-stocked" in result["speech"].lower() or "no purchase orders are needed" in result["speech"].lower()
    assert result["data"]["status"] == "none_needed"
    assert result["data"]["draft_id"] is None


@pytest.mark.django_db(transaction=True)
def test_planner_mode_mock_default():
    """Verify planner_mode is 'mock' when AWS_MOCK_MODE is true (default)."""
    session_id = "test_planner_mock_mode"
    prompt = "Restock low stock items"

    result = ERPPlannerAgent.plan_and_execute(prompt=prompt, session_id=session_id)

    assert result["planner_mode"] == "mock"
    assert result["data"]["planner_mode"] == "mock"
    assert result["data"]["mock_mode"] is True


@pytest.mark.django_db(transaction=True)
def test_bedrock_tool_use_loop_happy_path(monkeypatch):
    """Verify genuine Bedrock Converse tool-use loop: model calls tools, returns draft, final speech with draft ID."""
    from unittest.mock import MagicMock

    monkeypatch.setenv("AWS_MOCK_MODE", "false")

    # Get real low-stock items from DB
    all_low = [i for i in Item.objects.select_related("supplier").all() if i.is_below_reorder_level]
    target_skus = [i.sku for i in all_low[:2]] if all_low else ["SKU-1001"]

    mock_client = MagicMock()

    def fake_converse(**kwargs):
        messages = kwargs.get("messages", [])
        turn_num = (len(messages) + 1) // 2

        if turn_num == 1:
            # Model asks to check low stock items and supplier lead times
            return {
                "stopReason": "tool_use",
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "toolUse": {
                                    "toolUseId": "call_1",
                                    "name": "get_low_stock_items",
                                    "input": {},
                                }
                            },
                            {
                                "toolUse": {
                                    "toolUseId": "call_2",
                                    "name": "get_supplier_lead_times",
                                    "input": {},
                                }
                            },
                        ],
                    }
                },
            }
        elif turn_num == 2:
            # Model asks to draft purchase order for target SKUs
            return {
                "stopReason": "tool_use",
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "toolUse": {
                                    "toolUseId": "call_3",
                                    "name": "draft_purchase_order",
                                    "input": {"item_skus": target_skus},
                                }
                            }
                        ],
                    }
                },
            }
        else:
            # Model completes with end_turn and mentions draft ID
            last_user_content = messages[-1].get("content", [])
            created_draft_id = "DRAFT-PO-1"
            for b in last_user_content:
                tool_res = b.get("toolResult", {}).get("content", [{}])[0].get("json", {})
                if "draft_id" in tool_res:
                    created_draft_id = tool_res["draft_id"]

            return {
                "stopReason": "end_turn",
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "text": f"I analyzed inventory and created replenishment draft {created_draft_id} for {len(target_skus)} items. Would you like me to confirm it?"
                            }
                        ],
                    }
                },
            }

    mock_client.converse.side_effect = fake_converse
    monkeypatch.setattr(AWSConfig, "get_bedrock_runtime_client", lambda region_name=None: mock_client)

    session_id = "test_bedrock_tool_use_happy_path"
    prompt = "Restock everything that's running low from the fastest supplier"

    result = ERPPlannerAgent.plan_and_execute(prompt=prompt, session_id=session_id)

    # 1. Planner mode must be "bedrock"
    assert result["planner_mode"] == "bedrock"
    assert result["data"]["planner_mode"] == "bedrock"
    assert result["data"]["mock_mode"] is False
    assert AWSConfig.get_last_live_call() == "ok"

    # 2. Bedrock Converse call count
    assert result["bedrock_calls"] == 3
    assert result["data"]["bedrock_calls"] == 3
    assert result["latency_ms"] >= 0

    # 3. Plan steps built from actual tool calls
    plan_steps = result["data"]["plan_steps"]
    assert len(plan_steps) == 3
    assert "get_low_stock_items" in plan_steps[0]
    assert "get_supplier_lead_times" in plan_steps[1]
    assert "draft_purchase_order" in plan_steps[2]

    # 4. Draft order created in DB with status 'draft'
    draft_id = result["data"]["draft_id"]
    assert draft_id is not None
    assert draft_id.startswith("DRAFT-PO-")
    for po_id in result["data"]["po_ids"]:
        po = PurchaseOrder.objects.get(id=po_id)
        assert po.status == "draft"

    # 5. Model final speech contains draft ID
    assert draft_id.lower() in result["speech"].lower()
    assert "confirm" in result["speech"].lower()

    # 6. Session staged for confirmation
    pending = VoiceSessionService.get_pending_action(session_id)
    assert pending is not None
    assert pending["type"] == "confirm_purchase_order"
    assert pending["draft_id"] == draft_id


@pytest.mark.django_db(transaction=True)
def test_bedrock_model_asks_unauthorized_tool(monkeypatch):
    """Verify guardrail refuses unauthorized tool requested by the model and falls back."""
    from unittest.mock import MagicMock

    monkeypatch.setenv("AWS_MOCK_MODE", "false")

    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "stopReason": "tool_use",
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "unauth_call_1",
                            "name": "delete_all_inventory",
                            "input": {},
                        }
                    }
                ],
            }
        },
    }

    # Turn 2 completes turn after seeing error toolResult
    def fake_converse(**kwargs):
        messages = kwargs.get("messages", [])
        if len(messages) == 1:
            return mock_client.converse.return_value
        return {
            "stopReason": "end_turn",
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": "Unauthorized tool failed."}],
                }
            },
        }

    mock_client.converse.side_effect = fake_converse
    monkeypatch.setattr(AWSConfig, "get_bedrock_runtime_client", lambda region_name=None: mock_client)

    session_id = "test_bedrock_unauth_tool"
    prompt = "Delete all warehouse inventory"

    result = ERPPlannerAgent.plan_and_execute(prompt=prompt, session_id=session_id)

    # Must fall back because no valid tool calls were made
    assert result["planner_mode"] == "fallback"
    assert "without making valid tool calls" in result["fallback_reason"].lower()
    assert result["data"]["draft_id"] is not None  # Fallback planner still handled it safely


@pytest.mark.django_db(transaction=True)
def test_bedrock_model_asks_confirm_tool_refused(monkeypatch):
    """Verify guardrail strictly refuses confirm_purchase_order or approval tools if model tries to invoke them."""
    from unittest.mock import MagicMock

    monkeypatch.setenv("AWS_MOCK_MODE", "false")

    mock_client = MagicMock()

    def fake_converse(**kwargs):
        messages = kwargs.get("messages", [])
        if len(messages) == 1:
            # Model audaciously attempts to execute confirm_purchase_order
            return {
                "stopReason": "tool_use",
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "toolUse": {
                                    "toolUseId": "confirm_call_1",
                                    "name": "confirm_purchase_order",
                                    "input": {"draft_id": "DRAFT-PO-99"},
                                }
                            }
                        ],
                    }
                },
            }
        else:
            return {
                "stopReason": "end_turn",
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [{"text": "I was unable to confirm the order directly."}],
                    }
                },
            }

    mock_client.converse.side_effect = fake_converse
    monkeypatch.setattr(AWSConfig, "get_bedrock_runtime_client", lambda region_name=None: mock_client)

    session_id = "test_bedrock_confirm_refusal"
    prompt = "Immediately confirm purchase order 99"

    result = ERPPlannerAgent.plan_and_execute(prompt=prompt, session_id=session_id)

    # Must fall back because confirm tool was refused (no valid tool calls)
    assert result["planner_mode"] == "fallback"
    assert "without making valid tool calls" in result["fallback_reason"].lower()


@pytest.mark.django_db(transaction=True)
def test_bedrock_model_invalid_sku_handled(monkeypatch):
    """Verify Python guardrail validates that requested SKUs exist in DB and returns error on invalid SKU."""
    from unittest.mock import MagicMock

    monkeypatch.setenv("AWS_MOCK_MODE", "false")

    mock_client = MagicMock()

    def fake_converse(**kwargs):
        messages = kwargs.get("messages", [])
        if len(messages) == 1:
            return {
                "stopReason": "tool_use",
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "toolUse": {
                                    "toolUseId": "call_inv_sku",
                                    "name": "draft_purchase_order",
                                    "input": {"item_skus": ["FAKE-NON-EXISTENT-SKU-999"]},
                                }
                            }
                        ],
                    }
                },
            }
        else:
            return {
                "stopReason": "end_turn",
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [{"text": "SKU was not found in inventory."}],
                    }
                },
            }

    mock_client.converse.side_effect = fake_converse
    monkeypatch.setattr(AWSConfig, "get_bedrock_runtime_client", lambda region_name=None: mock_client)

    session_id = "test_bedrock_invalid_sku"
    prompt = "Restock FAKE-NON-EXISTENT-SKU-999"

    result = ERPPlannerAgent.plan_and_execute(prompt=prompt, session_id=session_id)

    # No valid draft could be created, so falls back to local deterministic planner
    assert result["planner_mode"] == "fallback"
    assert "without making valid tool calls" in result["fallback_reason"].lower()


@pytest.mark.django_db(transaction=True)
def test_bedrock_timeout_fallback(monkeypatch):
    """Verify Bedrock client timeout immediately triggers fallback with transparent reason."""
    from unittest.mock import MagicMock
    from botocore.exceptions import ReadTimeoutError

    monkeypatch.setenv("AWS_MOCK_MODE", "false")

    mock_client = MagicMock()
    mock_client.converse.side_effect = ReadTimeoutError(
        endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com",
        error=Exception("Read timed out"),
    )
    monkeypatch.setattr(AWSConfig, "get_bedrock_runtime_client", lambda region_name=None: mock_client)

    session_id = "test_bedrock_timeout"
    prompt = "Restock everything that's running low"

    result = ERPPlannerAgent.plan_and_execute(prompt=prompt, session_id=session_id)

    assert result["planner_mode"] == "fallback"
    assert result["data"]["planner_mode"] == "fallback"
    assert AWSConfig.get_last_live_call() == "failed"
    assert "timeout" in result["fallback_reason"].lower() or "readtimeouterror" in result["fallback_reason"].lower()
    # Safe local draft is still formed
    assert result["data"]["draft_id"] is not None


@pytest.mark.django_db(transaction=True)
def test_planner_mode_fallback_on_bedrock_error(monkeypatch, caplog):
    """Verify planner_mode is 'fallback', a WARNING is logged, and error reason is included when Bedrock fails."""
    import logging
    from unittest.mock import MagicMock

    monkeypatch.setenv("AWS_MOCK_MODE", "false")

    mock_client = MagicMock()
    error_msg = "AccessDeniedException: User is not authorized to perform bedrock:Converse on resource"
    mock_client.converse.side_effect = RuntimeError(error_msg)

    monkeypatch.setattr(AWSConfig, "get_bedrock_runtime_client", lambda region_name=None: mock_client)

    session_id = "test_bedrock_fallback_session"
    prompt = "Restock everything running low from the fastest supplier"

    with caplog.at_level(logging.WARNING):
        result = ERPPlannerAgent.plan_and_execute(prompt=prompt, session_id=session_id)

    # 1. Verify planner_mode is fallback
    assert result["planner_mode"] == "fallback"
    assert result["data"]["planner_mode"] == "fallback"
    assert result["data"]["mock_mode"] is True
    assert AWSConfig.get_last_live_call() == "failed"
    assert result["bedrock_calls"] == 1
    assert result["data"]["bedrock_calls"] == 1
    assert result["latency_ms"] >= 0

    # 2. Verify error reason is present in both root and data
    assert error_msg in result["fallback_reason"]
    assert error_msg in result["data"]["fallback_reason"]
    assert error_msg in result["data"]["bedrock_error"]

    # 3. Verify clear WARNING log was emitted
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_records) >= 1
    assert any("Bedrock" in r.message and "AccessDeniedException" in r.message for r in warning_records)

    # 4. Verify local planner still drafted orders safely
    assert result["data"]["draft_id"] is not None
    assert result["data"]["status"] == "draft"


@pytest.mark.django_db(transaction=True)
def test_planner_mode_fallback_on_client_init_none(monkeypatch, caplog):
    """Verify fallback mode activates if get_bedrock_runtime_client returns None when live mode is requested."""
    import logging

    monkeypatch.setenv("AWS_MOCK_MODE", "false")
    monkeypatch.setattr(AWSConfig, "get_bedrock_runtime_client", lambda region_name=None: None)

    session_id = "test_bedrock_client_none_session"
    prompt = "Restock low stock items"

    with caplog.at_level(logging.WARNING):
        result = ERPPlannerAgent.plan_and_execute(prompt=prompt, session_id=session_id)

    assert result["planner_mode"] == "fallback"
    assert result["data"]["planner_mode"] == "fallback"
    assert "fallback_reason" in result
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_suggest_inference_profile():
    """Verify suggest_inference_profile returns expected cross-region profile IDs."""
    from aws_planner.check import suggest_inference_profile

    assert suggest_inference_profile("amazon.nova-micro-v1:0") == "us.amazon.nova-micro-v1:0"
    assert suggest_inference_profile("amazon.nova-lite-v1:0") == "us.amazon.nova-lite-v1:0"
    assert suggest_inference_profile("us.amazon.nova-micro-v1:0") == "us.amazon.nova-micro-v1:0"
    assert "us." in suggest_inference_profile("anthropic.claude-3-5-sonnet-20241022-v2:0")


def test_check_bedrock_command_success(monkeypatch, capsys):
    """Verify check_bedrock returns code 0 and prints region, model, auth method, latency and reply."""
    from unittest.mock import MagicMock
    import boto3
    from aws_planner.check import check_bedrock

    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {"message": {"content": [{"text": "Hello from Bedrock!"}]}}
    }
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: mock_client)

    exit_code = check_bedrock()
    assert exit_code == 0
    assert AWSConfig.get_last_live_call() == "ok"

    captured = capsys.readouterr()
    assert "SUCCESS" in captured.out
    assert "Hello from Bedrock!" in captured.out
    assert "Latency" in captured.out
    assert "Auth Method:" in captured.out
    assert "Model ID" in captured.out
    assert "AWS Region" in captured.out


def test_check_bedrock_command_inference_profile_guidance(monkeypatch, capsys):
    """Verify check_bedrock recommends exact inference profile ID on on-demand error."""
    from unittest.mock import MagicMock
    import boto3
    from aws_planner.check import check_bedrock

    mock_client = MagicMock()
    mock_client.converse.side_effect = RuntimeError(
        "Invocation of model ID amazon.nova-micro-v1:0 with on-demand throughput isn't supported. "
        "Retry your request with the ID or ARN of an inference profile"
    )
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: mock_client)

    exit_code = check_bedrock()
    assert exit_code == 1
    assert AWSConfig.get_last_live_call() == "failed"

    captured = capsys.readouterr()
    assert "FAILED" in captured.out
    assert "us.amazon.nova-micro-v1:0" in captured.out
    assert "BEDROCK_MODEL_ID=us.amazon.nova-micro-v1:0" in captured.out


def test_check_bedrock_command_scp_deny_guidance(monkeypatch, capsys):
    """Verify check_bedrock provides clear guidance when SCP explicitly denies CallWithBearerToken."""
    from unittest.mock import MagicMock
    import boto3
    from aws_planner.check import check_bedrock

    mock_client = MagicMock()
    mock_client.converse.side_effect = RuntimeError(
        "User is not authorized to perform: bedrock:CallWithBearerToken with an explicit deny in a service control policy"
    )
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: mock_client)

    exit_code = check_bedrock()
    assert exit_code == 1
    assert AWSConfig.get_last_live_call() == "failed"

    captured = capsys.readouterr()
    assert "FAILED" in captured.out
    assert "Service Control Policy" in captured.out or "SCP" in captured.out
    assert "AmazonBedrockLimitedAccess" in captured.out


def test_bedrock_runtime_client_explicit_timeouts_and_retries(monkeypatch):
    """Verify get_bedrock_runtime_client configures 5s connect, 20s read timeouts, and max 1 retry."""
    from unittest.mock import MagicMock
    import boto3

    monkeypatch.setenv("AWS_MOCK_MODE", "false")

    captured_config = {}

    def mock_boto_client(service_name, **kwargs):
        captured_config["service_name"] = service_name
        captured_config["config"] = kwargs.get("config")
        return MagicMock()

    monkeypatch.setattr(boto3, "client", mock_boto_client)

    client = AWSConfig.get_bedrock_runtime_client()
    assert client is not None
    assert captured_config["service_name"] == "bedrock-runtime"
    cfg = captured_config["config"]
    assert cfg is not None
    assert cfg.connect_timeout == 5
    assert cfg.read_timeout == 20
    assert cfg.retries.get("max_attempts") == 2
