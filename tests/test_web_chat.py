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
