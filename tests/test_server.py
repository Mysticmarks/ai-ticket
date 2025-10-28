from __future__ import annotations

import json
import time

import pytest

from ai_ticket import server
from ai_ticket.events.inference import CompletionResponse, ErrorResponse
from ai_ticket.metrics import CONTENT_TYPE_LATEST
from ai_ticket.observability.metrics import MetricsStore
from ai_ticket.security import InMemoryRateLimiter
from ai_ticket.server import app as flask_app


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
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = CompletionResponse(completion="Test completion")

    payload = {"content": {"prompt": "Test prompt"}}
    response = client.post("/event", json=payload)

    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data == {"completion": "Test completion"}
    mock_on_event.assert_called_once_with(payload)


def test_handle_event_missing_content(client, mocker):
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = ErrorResponse(
        error="missing_content_field",
        message="The 'content' field is required.",
        status_code=400,
        details="'content' field is missing...",
    )

    payload = {"some_other_key": "some_value"}
    response = client.post("/event", json=payload)

    assert response.status_code == 400
    response_data = json.loads(response.data)
    assert response_data["error"] == "missing_content_field"
    mock_on_event.assert_called_once_with(payload)


def test_handle_event_not_json(client, mocker):
    mock_on_event = mocker.patch("ai_ticket.server.on_event")

    response = client.post("/event", data="not a json string", content_type="text/plain")

    assert response.status_code == 400
    response_data = json.loads(response.data)
    assert response_data["error"] == "invalid_request"
    assert "Request must be JSON" in response_data["details"]
    mock_on_event.assert_not_called()


def test_handle_event_on_event_error(client, mocker):
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = ErrorResponse(
        error="api_connection_error",
        message="Could not connect",
        status_code=503,
        details="Could not connect",
    )

    payload = {"content": {"prompt": "Test prompt for API error"}}
    response = client.post("/event", json=payload)

    assert response.status_code == 503
    response_data = json.loads(response.data)
    assert response_data["error"] == "api_connection_error"
    mock_on_event.assert_called_once_with(payload)


def test_handle_event_prompt_extraction_failed(client, mocker):
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = ErrorResponse(
        error="prompt_extraction_failed",
        message="Could not derive prompt.",
        status_code=422,
        details="Could not derive prompt.",
    )

    payload = {"content": {"unexpected_structure": True}}
    response = client.post("/event", json=payload)

    assert response.status_code == 422
    response_data = json.loads(response.data)
    assert response_data["error"] == "prompt_extraction_failed"
    mock_on_event.assert_called_once_with(payload)


@pytest.mark.failure_mode
def test_missing_authentication_token(client, mocker):
    mocker.patch("ai_ticket.server.on_event").return_value = CompletionResponse(completion="ok")
    server.TOKEN_MANAGER.update_tokens({"secret-token"})

    response = client.post("/event", json={"content": {"prompt": "needs auth"}})

    assert response.status_code == 401
    data = json.loads(response.data)
    assert data["error"] == "unauthorised"


@pytest.mark.failure_mode
def test_invalid_bearer_token_rejected(client, mocker):
    mocker.patch("ai_ticket.server.on_event").return_value = CompletionResponse(completion="ok")
    server.TOKEN_MANAGER.update_tokens({"secret-token"})

    response = client.post(
        "/event",
        json={"content": {"prompt": "authorised"}},
        headers={"Authorization": "Bearer totally-wrong"},
    )

    assert response.status_code == 403
    data = json.loads(response.data)
    assert data["error"] == "forbidden"
    assert "Invalid authentication token" in data["details"]


def test_valid_bearer_token_allows_request(client, mocker):
    mocker.patch("ai_ticket.server.on_event").return_value = CompletionResponse(completion="secure")
    server.TOKEN_MANAGER.update_tokens({"secret-token"})

    response = client.post(
        "/event",
        json={"content": {"prompt": "authorised"}},
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["completion"] == "secure"


def test_metrics_endpoint_available(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.content_type == CONTENT_TYPE_LATEST


@pytest.mark.failure_mode
def test_rate_limiter_blocks_when_threshold_exceeded(client, mocker):
    mocker.patch("ai_ticket.server.on_event").return_value = CompletionResponse(completion="ok")
    original = server.RATE_LIMITER
    server.RATE_LIMITER = InMemoryRateLimiter(limit=1, window_seconds=60)

    try:
        first = client.post(
            "/event",
            json={"content": {"prompt": "first"}},
            headers={"X-Forwarded-For": "1.1.1.1"},
        )
        assert first.status_code == 200

        second = client.post(
            "/event",
            json={"content": {"prompt": "second"}},
            headers={"X-Forwarded-For": "1.1.1.1"},
        )
        assert second.status_code == 429
        data = json.loads(second.data)
        assert data["error"] == "rate_limited"
        retry_after = second.headers.get("Retry-After")
        assert retry_after is not None
        assert int(retry_after) >= 0
    finally:
        server.RATE_LIMITER = original


def test_metrics_stream_emits_updates(client, monkeypatch):
    fresh_store = MetricsStore()
    monkeypatch.setattr(server, "metrics_store", fresh_store)

    response = client.get("/api/metrics/stream")
    stream = iter(response.response)
    first_chunk = next(stream).decode()
    assert first_chunk.startswith("data: ")

    fresh_store.record_event(latency_s=0.05, success=True)
    second_chunk = next(stream).decode()
    assert '"successes": 1' in second_chunk
    response.close()


@pytest.mark.failure_mode
def test_metrics_stream_reconnects_after_client_drop(client, monkeypatch):
    fresh_store = MetricsStore()
    monkeypatch.setattr(server, "metrics_store", fresh_store)

    first_response = client.get("/api/metrics/stream")
    first_stream = iter(first_response.response)
    next(first_stream)
    assert len(fresh_store._subscribers) == 1

    first_response.close()

    def _wait_for_unsubscribe(timeout: float = 0.5) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not fresh_store._subscribers:
                return True
            time.sleep(0.01)
        return not fresh_store._subscribers

    assert _wait_for_unsubscribe()

    second_response = client.get("/api/metrics/stream")
    second_stream = iter(second_response.response)
    initial_chunk = next(second_stream).decode()
    assert initial_chunk.startswith("data: ")

    fresh_store.record_event(
        latency_s=0.02,
        success=False,
        error_code="rate_limited",
        message="burst",
    )
    follow_up = next(second_stream).decode()
    assert '"rate_limited"' in follow_up

    second_response.close()
    assert _wait_for_unsubscribe()
