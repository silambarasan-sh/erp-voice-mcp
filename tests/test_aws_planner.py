"""Tests for the Amazon Bedrock and Strands ERP Planner Agent."""

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
    yield
    VoiceSessionService.reset()


def test_aws_config_defaults_and_env():
    """Verify AWS region, model ID, and mock mode configuration."""
    assert AWSConfig.get_region() is not None
    assert "amazon" in AWSConfig.get_model_id().lower() or "claude" in AWSConfig.get_model_id().lower()
    assert AWSConfig.is_mock_mode() is True  # Default for testing/demo


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
def test_planner_mode_bedrock_live_success(monkeypatch):
    """Verify planner_mode is 'bedrock' when live Bedrock converse call succeeds."""
    from unittest.mock import MagicMock

    monkeypatch.setenv("AWS_MOCK_MODE", "false")

    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "stopReason": "end_turn",
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "Formulated replenishment plan using Bedrock."}],
            }
        },
    }

    monkeypatch.setattr(AWSConfig, "get_bedrock_runtime_client", lambda region_name=None: mock_client)

    session_id = "test_bedrock_live_session"
    prompt = "Restock everything running low from the fastest supplier"

    result = ERPPlannerAgent.plan_and_execute(prompt=prompt, session_id=session_id)

    assert result["planner_mode"] == "bedrock"
    assert result["data"]["planner_mode"] == "bedrock"
    assert result["data"]["mock_mode"] is False
    assert result["data"]["bedrock_response_status"] == "end_turn"
    assert mock_client.converse.called is True
    assert "draft_id" in result["data"]


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
