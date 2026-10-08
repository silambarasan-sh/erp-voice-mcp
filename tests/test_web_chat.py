"""Tests for the Alexa+ Web Chat simulator interface and endpoints."""

import pytest
from starlette.testclient import TestClient
from mcp_server.app import create_app


@pytest.fixture
def web_client():
    """Create a TestClient with the Starlette app."""
    return TestClient(create_app())


@pytest.mark.django_db(transaction=True)
def test_chat_page_endpoint(web_client):
    """Verify GET /chat serves the Alexa+ HTML web simulator."""
    response = web_client.get("/chat")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "Alexa+ ERP Voice Assistant" in html
    assert "id=\"voice-mic-btn\"" in html
    assert "id=\"chat-input\"" in html
    assert "id=\"conversation-view\"" in html
    assert "SpeechSynthesisUtterance" in html
    assert "webkitSpeechRecognition" in html


@pytest.mark.django_db(transaction=True)
def test_root_serves_html_for_browser_clients(web_client):
    """Verify GET / returns HTML when Accept header includes text/html."""
    response = web_client.get("/", headers={"Accept": "text/html,application/xhtml+xml"})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Alexa+ ERP" in response.text


@pytest.mark.django_db(transaction=True)
def test_chat_api_routing_replenishment(web_client):
    """Verify POST /api/chat routes replenishment prompts to Bedrock planner."""
    payload = {
        "message": "Restock everything that's running low from the fastest supplier",
        "session_id": "test_web_chat_replenish",
    }
    response = web_client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["tool"] == "plan_erp_replenishment"
    assert data["planner_mode"] == "mock"
    assert data["data"]["planner_mode"] == "mock"
    assert "speech" in data
    assert "data" in data
    assert data["data"]["draft_id"] is not None
    assert "plan_steps" in data["data"]


@pytest.mark.django_db(transaction=True)
def test_chat_api_routing_pending_invoices(web_client):
    """Verify POST /api/chat routes invoice queries and returns structured data."""
    payload = {
        "message": "What are my pending invoices for October?",
        "session_id": "test_web_chat_invoices",
    }
    response = web_client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["tool"] == "get_pending_invoices"
    assert "pending invoices" in data["speech"].lower()
    assert data["data"]["count"] > 0
    assert "invoices" in data["data"]


@pytest.mark.django_db(transaction=True)
def test_chat_api_routing_confirm_action(web_client):
    """Verify POST /api/chat routes 'confirm it' to confirm_action."""
    payload = {
        "message": "confirm it",
        "session_id": "test_web_chat_confirm",
    }
    response = web_client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["tool"] == "confirm_action"
    assert "speech" in data


@pytest.mark.django_db(transaction=True)
def test_tool_api_direct_call(web_client):
    """Verify POST /api/tool allows direct tool invocation for card buttons."""
    payload = {
        "tool_name": "get_low_stock_items",
        "arguments": {},
        "session_id": "test_direct_tool",
    }
    response = web_client.post("/api/tool", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["tool"] == "get_low_stock_items"
    assert "items" in data["data"]


@pytest.mark.django_db(transaction=True)
def test_chat_page_labels_honest_in_mock_mode(web_client):
    """Verify header text and Restock button do not claim Bedrock when in default mock mode."""
    import re
    response = web_client.get("/chat")
    assert response.status_code == 200
    html = response.text

    # Header subtext should be Supply Chain Planner, not Bedrock
    header_match = re.search(r'<small id="header-planner-subtext"[^>]*>(.*?)</small>', html, re.DOTALL)
    assert header_match is not None
    header_text = header_match.group(1).strip()
    assert "Supply Chain Planner" in header_text
    assert "Bedrock" not in header_text

    # Restock chip button should NOT say Bedrock
    btn_match = re.search(r'<button class="chip-btn" id="chip-restock-btn"[^>]*>(.*?)</button>', html, re.DOTALL)
    assert btn_match is not None
    btn_text = btn_match.group(1).strip()
    assert "Restock Fastest Supplier" in btn_text
    assert "Bedrock" not in btn_text


@pytest.mark.django_db(transaction=True)
def test_chat_api_routing_greeting(web_client):
    """Verify greeting inputs return short hello and exactly 3 example questions."""
    for phrase in ["Hello", "vanakkam", "hi", "hey there"]:
        response = web_client.post("/api/chat", json={"message": phrase, "session_id": "test_greeting"})
        assert response.status_code == 200
        data = response.json()
        assert data["tool"] == "greeting"
        assert "hello" in data["speech"].lower()
        assert len(data["data"]["examples"]) == 3
        assert "pending invoices" in data["speech"].lower()
        assert "low stock" in data["speech"].lower()
        assert "restock" in data["speech"].lower()


@pytest.mark.django_db(transaction=True)
def test_chat_api_routing_thanks(web_client):
    """Verify thanks/closing inputs return polite closing with no data."""
    for phrase in ["thank you", "thanks", "ok", "okay", "bye"]:
        response = web_client.post("/api/chat", json={"message": phrase, "session_id": "test_thanks"})
        assert response.status_code == 200
        data = response.json()
        assert data["tool"] == "thanks"
        assert len(data["speech"]) > 0
        assert not data["data"]  # Empty dict / no data


@pytest.mark.django_db(transaction=True)
def test_chat_api_routing_gibberish_fallback(web_client):
    """Verify gibberish input does NOT return daily briefing but polite fallback with capabilities and 2 examples."""
    response = web_client.post("/api/chat", json={"message": "asdf", "session_id": "test_gibberish"})
    assert response.status_code == 200
    data = response.json()
    assert data["tool"] == "unrecognized"
    assert data["tool"] != "voice_daily_erp_briefing"
    assert "briefing" not in data["tool"]
    # Check capabilities mentioned in fallback
    speech_lower = data["speech"].lower()
    for cap in ["invoices", "stock", "leaves", "restock", "top customers"]:
        assert cap in speech_lower
    assert len(data["data"]["examples"]) == 2


@pytest.mark.django_db(transaction=True)
def test_chat_api_routing_off_topic_fallback(web_client):
    """Verify off-topic questions route to unrecognized fallback, NEVER to daily briefing."""
    response = web_client.post("/api/chat", json={"message": "what is the weather", "session_id": "test_weather"})
    assert response.status_code == 200
    data = response.json()
    assert data["tool"] == "unrecognized"
    assert data["tool"] != "voice_daily_erp_briefing"
    assert "briefing" not in data["tool"]
    assert "invoices" in data["speech"].lower()


@pytest.mark.django_db(transaction=True)
def test_chat_api_routing_help(web_client):
    """Verify 'what can you do' routes to help intent."""
    response = web_client.post("/api/chat", json={"message": "what can you do", "session_id": "test_help"})
    assert response.status_code == 200
    data = response.json()
    assert data["tool"] == "help"
    assert "capabilities" in data["data"]


@pytest.mark.django_db(transaction=True)
def test_chat_api_routing_daily_briefing_explicit_only(web_client):
    """Verify daily briefing is ONLY returned when explicit briefing/overview/summary is requested."""
    for phrase in [
        "give me the daily briefing",
        "daily briefing",
        "system overview",
        "executive summary",
        "erp status",
        "overall status",
        "what's happening today",
    ]:
        response = web_client.post("/api/chat", json={"message": phrase, "session_id": "test_briefing"})
        assert response.status_code == 200
        data = response.json()
        assert data["tool"] == "voice_daily_erp_briefing"
        assert "speech" in data
        assert "data" in data


@pytest.mark.django_db(transaction=True)
def test_chat_api_routing_status_alone_hits_polite_fallback(web_client):
    """Verify the bare word 'status' does NOT trigger daily briefing, but hits polite fallback."""
    response = web_client.post("/api/chat", json={"message": "status", "session_id": "test_bare_status"})
    assert response.status_code == 200
    data = response.json()
    assert data["tool"] == "unrecognized"
    assert data["tool"] != "voice_daily_erp_briefing"
    assert "briefing" not in data["tool"]
    assert "invoices" in data["speech"].lower()


@pytest.mark.django_db(transaction=True)
def test_chat_api_routing_purchase_order_status(web_client):
    """Verify 'PO status', 'purchase order status', and 'draft POs' route to get_purchase_order_status."""
    for phrase in ["PO status", "purchase order status", "draft POs", "pending POs", "show purchase orders", "how many POs"]:
        response = web_client.post("/api/chat", json={"message": phrase, "session_id": "test_po_status"})
        assert response.status_code == 200
        data = response.json()
        assert data["tool"] == "get_purchase_order_status"
        assert data["tool"] != "voice_daily_erp_briefing"
        assert data["tool"] != "draft_purchase_order"
        assert "purchase orders" in data["speech"].lower()
        assert "total_count" in data["data"]
        assert "draft_count" in data["data"]
        assert "confirmed_count" in data["data"]
        assert "recent_orders" in data["data"]


@pytest.mark.django_db(transaction=True)
def test_chat_api_routing_confirm_vs_thanks(web_client):
    """Verify 'okay confirm it' and 'ok confirm' route to confirm_action, while bare 'ok' gets thanks."""
    # Confirm variations
    for phrase in ["okay confirm it", "ok confirm", "confirm it"]:
        response = web_client.post("/api/chat", json={"message": phrase, "session_id": "test_confirm_var"})
        assert response.status_code == 200
        data = response.json()
        assert data["tool"] == "confirm_action"

    # Bare "ok" -> thanks / closing
    response_ok = web_client.post("/api/chat", json={"message": "ok", "session_id": "test_ok_bare"})
    assert response_ok.status_code == 200
    data_ok = response_ok.json()
    assert data_ok["tool"] == "thanks"
    assert not data_ok["data"]


@pytest.mark.django_db(transaction=True)
def test_chat_api_routing_other_thing_status_queries(web_client):
    """Verify '<thing> status' queries route to their own specific domain tool first."""
    # Leave status -> get_pending_leaves
    res_leave = web_client.post("/api/chat", json={"message": "leave status", "session_id": "test_thing_status"})
    assert res_leave.status_code == 200
    assert res_leave.json()["tool"] == "get_pending_leaves"

    res_pending_leave = web_client.post("/api/chat", json={"message": "pending leave status", "session_id": "test_thing_status"})
    assert res_pending_leave.status_code == 200
    assert res_pending_leave.json()["tool"] == "get_pending_leaves"

    # Invoice status -> get_pending_invoices
    res_inv = web_client.post("/api/chat", json={"message": "invoice status", "session_id": "test_thing_status"})
    assert res_inv.status_code == 200
    assert res_inv.json()["tool"] == "get_pending_invoices"

    # Stock status -> get_low_stock_items
    res_stock = web_client.post("/api/chat", json={"message": "stock status", "session_id": "test_thing_status"})
    assert res_stock.status_code == 200
    assert res_stock.json()["tool"] == "get_low_stock_items"


@pytest.mark.django_db(transaction=True)
def test_chat_api_routing_low_stock_items(web_client):
    """Verify low stock queries continue routing to get_low_stock_items."""
    response = web_client.post("/api/chat", json={"message": "check low stock items", "session_id": "test_low_stock"})
    assert response.status_code == 200
    data = response.json()
    assert data["tool"] == "get_low_stock_items"
    assert "items" in data["data"]


