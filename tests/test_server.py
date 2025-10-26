import pytest
import json
from src.ai_ticket.server import app as flask_app # Import the Flask app instance

@pytest.fixture
def app():
    yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()

def test_handle_event_success(client, mocker):
    # Mock the on_event function to avoid actual backend calls
    mock_on_event = mocker.patch('src.ai_ticket.server.on_event')
    mock_on_event.return_value = {"completion": "Test completion"}

    payload = {"content": "Test prompt"}
    response = client.post("/event", json=payload)

    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data == {"completion": "Test completion"}
    mock_on_event.assert_called_once_with(payload)

def test_handle_event_missing_content(client, mocker):
    mock_on_event = mocker.patch('src.ai_ticket.server.on_event')

    payload = {"some_other_key": "some_value"}  # Missing 'content'
    response = client.post("/event", json=payload)

    assert response.status_code == 400
    response_data = json.loads(response.data)
    assert response_data["error"] == "invalid_request"
    assert "details" in response_data
    mock_on_event.assert_not_called()


def test_handle_event_not_json(client, mocker):
    # Mock on_event to ensure it's not called for non-JSON requests
    mock_on_event = mocker.patch('src.ai_ticket.server.on_event')

    response = client.post("/event", data="not a json string", content_type="text/plain")

    assert response.status_code == 400
    response_data = json.loads(response.data)
    assert response_data["error"] == "invalid_request"
    assert "Request must be JSON" in response_data["details"]
    mock_on_event.assert_not_called() # on_event should not be called if request is not JSON

def test_handle_event_on_event_error(client, mocker):
    # Test a scenario where on_event returns a specific error
    mock_on_event = mocker.patch('src.ai_ticket.server.on_event')
    mock_on_event.return_value = {"error": "api_connection_error", "details": "Could not connect"}

    payload = {"content": "Test prompt for API error"}
    response = client.post("/event", json=payload)

    assert response.status_code == 503
    response_data = json.loads(response.data)
    assert response_data["error"] == "api_connection_error"
    mock_on_event.assert_called_once_with(payload)

def test_handle_event_prompt_extraction_failed(client, mocker):
    mock_on_event = mocker.patch('src.ai_ticket.server.on_event')
    mock_on_event.return_value = {"error": "prompt_extraction_failed", "details": "Could not derive prompt."}

    payload = {"content": {"unexpected_structure": True}} # Example that might cause extraction failure
    response = client.post("/event", json=payload)

    assert response.status_code == 400 # Default error code for client-side issues
    response_data = json.loads(response.data)
    assert response_data["error"] == "prompt_extraction_failed"
    mock_on_event.assert_called_once_with(payload)


def test_readiness_probe_not_ready(monkeypatch, client):
    monkeypatch.setenv("KOBOLDCPP_API_URL", "")

    response = client.get("/readyz")

    assert response.status_code == 503
    body = json.loads(response.data)
    assert body["error"] == "service_unavailable"
    assert "koboldcpp_api_url_not_configured" in body["details"]["reasons"]


def test_readiness_probe_ready(monkeypatch, client):
    monkeypatch.setenv("KOBOLDCPP_API_URL", "http://example.com/api")

    response = client.get("/readyz")

    assert response.status_code == 200
    assert json.loads(response.data)["status"] == "ready"


def test_metrics_endpoint(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert b"ai_ticket_http_requests_total" in response.data
