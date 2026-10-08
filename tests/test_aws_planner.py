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
