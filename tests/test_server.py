import json

import pytest

from ai_ticket.server import app as flask_app

@pytest.fixture
def app():
    yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()

def test_handle_event_success(client, mocker):
    # Mock the on_event function to avoid actual backend calls
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = {"completion": "Test completion"}

    payload = {"content": "Test prompt"}
    response = client.post("/event", json=payload)

    assert response.status_code == 200
    response_data = response.get_json()
    assert response_data == {"completion": "Test completion"}
    mock_on_event.assert_called_once_with(payload)

def test_handle_event_missing_content(client, mocker):
    # Mock on_event to ensure it's not called if input validation fails early
    # or to control its return if server.py calls it before its own validation.
    # The current server.py calls on_event, so we mock its error return.
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = {
        "error": "missing_content_field",
        "details": "'content' field is missing in event data.",
    }

    payload = {"some_other_key": "some_value"} # Missing 'content'
    response = client.post("/event", json=payload)

    assert response.status_code == 400 # Assuming server.py maps this error to 400
    response_data = response.get_json()
    assert response_data["error"] == "missing_content_field"
    assert response_data["details"] == "'content' field is missing in event data."
    mock_on_event.assert_called_once_with(payload)


def test_handle_event_not_json(client, mocker):
    # Mock on_event to ensure it's not called for non-JSON requests
    mock_on_event = mocker.patch("ai_ticket.server.on_event")

    response = client.post("/event", data="not a json string", content_type="text/plain")

    assert response.status_code == 400
    response_data = response.get_json()
    assert response_data["error"] == "invalid_request"
    assert "Request must be JSON" in response_data["details"]
    mock_on_event.assert_not_called() # on_event should not be called if request is not JSON

def test_handle_event_on_event_error(client, mocker):
    # Test a scenario where on_event returns a specific error
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = {
        "error": "api_connection_error",
        "details": "Failed to connect to backend.",
    }

    payload = {"content": "Test prompt for API error"}
    response = client.post("/event", json=payload)

    assert response.status_code == 503 # As per server.py logic for this error
    response_data = response.get_json()
    assert response_data["error"] == "api_connection_error"
    assert response_data["details"] == "Failed to connect to backend."
    mock_on_event.assert_called_once_with(payload)

def test_handle_event_prompt_extraction_failed(client, mocker):
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = {
        "error": "prompt_extraction_failed",
        "details": "Could not derive prompt.",
    }

    payload = {"content": {"unexpected_structure": True}} # Example that might cause extraction failure
    response = client.post("/event", json=payload)

    assert response.status_code == 400 # Default error code for client-side issues
    response_data = response.get_json()
    assert response_data["error"] == "prompt_extraction_failed"
    assert response_data["details"] == "Could not derive prompt."
    mock_on_event.assert_called_once_with(payload)


def test_handle_event_malformed_json_payload(client, mocker):
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = {
        "error": "invalid_input_format",
        "details": "Event data must be a dictionary.",
    }

    response = client.post("/event", data=json.dumps(["not", "a", "dict"]), content_type="application/json")

    assert response.status_code == 400
    response_data = response.get_json()
    assert response_data == {
        "error": "invalid_input_format",
        "details": "Event data must be a dictionary.",
    }
    mock_on_event.assert_called_once_with(["not", "a", "dict"])


def test_handle_event_backend_timeout_maps_to_retry_details(client, mocker):
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = {
        "error": "api_connection_error",
        "details": "Failed to connect to KoboldCPP API after multiple attempts. Last error: Timeout",
    }

    payload = {"content": "prompt"}
    response = client.post("/event", json=payload)

    assert response.status_code == 503
    response_data = response.get_json()
    assert response_data["error"] == "api_connection_error"
    assert "multiple attempts" in response_data["details"]
    mock_on_event.assert_called_once_with(payload)


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "healthy"}
