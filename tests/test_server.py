import json
import pytest

from ai_ticket.events.inference import CompletionResponse, ErrorResponse
from ai_ticket.metrics import CONTENT_TYPE_LATEST
from ai_ticket.observability.metrics import MetricsStore
from ai_ticket.security import InMemoryRateLimiter
from src.ai_ticket import server
from src.ai_ticket.server import app as flask_app # Import the Flask app instance

@pytest.fixture
def app():
    yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def reset_auth_tokens():
    original_tokens = server.TOKEN_MANAGER.tokens
    yield
    server.TOKEN_MANAGER.update_tokens(original_tokens)

def test_handle_event_success(client, mocker):
    # Mock the on_event function to avoid actual backend calls
    mock_on_event = mocker.patch('src.ai_ticket.server.on_event')
    mock_on_event.return_value = CompletionResponse(completion="Test completion")

    payload = {"content": "Test prompt"}
    response = client.post("/event", json=payload)

    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data == {"completion": "Test completion"}
    mock_on_event.assert_called_once_with(payload)

def test_handle_event_missing_content(client, mocker):
    # Mock on_event to ensure it's not called if input validation fails early
    # or to control its return if server.py calls it before its own validation.
    # The current server.py calls on_event, so we mock its error return.
    mock_on_event = mocker.patch('src.ai_ticket.server.on_event')
    mock_on_event.return_value = ErrorResponse(
        error="missing_content_field",
        message="The 'content' field is required.",
        status_code=400,
        details="'content' field is missing...",
    )

    payload = {"some_other_key": "some_value"} # Missing 'content'
    response = client.post("/event", json=payload)

    assert response.status_code == 400
    response_data = json.loads(response.data)
    assert response_data["error"] == "missing_content_field"
    mock_on_event.assert_called_once_with(payload)


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
    mock_on_event.return_value = ErrorResponse(
        error="api_connection_error",
        message="Could not connect",
        status_code=503,
        details="Could not connect",
    )

    payload = {"content": "Test prompt for API error"}
    response = client.post("/event", json=payload)

    assert response.status_code == 503
    response_data = json.loads(response.data)
    assert response_data["error"] == "api_connection_error"
    mock_on_event.assert_called_once_with(payload)

def test_handle_event_prompt_extraction_failed(client, mocker):
    mock_on_event = mocker.patch('src.ai_ticket.server.on_event')
    mock_on_event.return_value = ErrorResponse(
        error="prompt_extraction_failed",
        message="Could not derive prompt.",
        status_code=422,
        details="Could not derive prompt.",
    )

    payload = {"content": {"unexpected_structure": True}} # Example that might cause extraction failure
    response = client.post("/event", json=payload)

    assert response.status_code == 422
    response_data = json.loads(response.data)
    assert response_data["error"] == "prompt_extraction_failed"
    mock_on_event.assert_called_once_with(payload)


def test_missing_authentication_token(client, mocker):
    mocker.patch('src.ai_ticket.server.on_event').return_value = CompletionResponse(completion="ok")
    server.TOKEN_MANAGER.update_tokens({"secret-token"})

    response = client.post("/event", json={"content": "needs auth"})

    assert response.status_code == 401
    data = json.loads(response.data)
    assert data["error"] == "unauthorised"


def test_valid_bearer_token_allows_request(client, mocker):
    mocker.patch('src.ai_ticket.server.on_event').return_value = CompletionResponse(completion="secure")
    server.TOKEN_MANAGER.update_tokens({"secret-token"})

    response = client.post(
        "/event",
        json={"content": "authorised"},
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["completion"] == "secure"


def test_metrics_endpoint_available(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.content_type == CONTENT_TYPE_LATEST


def test_rate_limiter_blocks_when_threshold_exceeded(client, mocker):
    mocker.patch('src.ai_ticket.server.on_event').return_value = CompletionResponse(completion="ok")
    original = server.RATE_LIMITER
    server.RATE_LIMITER = InMemoryRateLimiter(limit=1, window_seconds=60)

    try:
        first = client.post("/event", json={"content": "first"}, headers={"X-Forwarded-For": "1.1.1.1"})
        assert first.status_code == 200

        second = client.post("/event", json={"content": "second"}, headers={"X-Forwarded-For": "1.1.1.1"})
        assert second.status_code == 429
        data = json.loads(second.data)
        assert data["error"] == "rate_limited"
    finally:
        server.RATE_LIMITER = original


def test_metrics_stream_emits_updates(client, mocker):
    fresh_store = MetricsStore()
    mocker.patch('src.ai_ticket.server.metrics_store', fresh_store)

    response = client.get('/api/metrics/stream')
    stream = iter(response.response)
    first_chunk = next(stream).decode()
    assert first_chunk.startswith('data: ')

    fresh_store.record_event(latency_s=0.05, success=True)
    second_chunk = next(stream).decode()
    assert '"successes": 1' in second_chunk
    response.close()


def test_diagnostics_self_test_endpoint(client):
    response = client.get("/diagnostics/self-test")

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] in {"ok", "warning"}
    assert isinstance(data.get("checks"), list)


def test_diagnostics_simulate_endpoint(client):
    server.TOKEN_MANAGER.update_tokens({"test-token"})

    response = client.post(
        "/diagnostics/simulate",
        json={"event": {"content": {"prompt": "diagnostic"}}},
    )

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] in {"ok", "warning"}
    assert any(step["name"] == "payload_validation" for step in data["steps"])


def test_diagnostics_simulate_rejects_invalid_payload(client):
    response = client.post("/diagnostics/simulate", json={"event": "invalid"})

    assert response.status_code == 400
    data = json.loads(response.data)
    assert data["error"] == "invalid_event_payload"
