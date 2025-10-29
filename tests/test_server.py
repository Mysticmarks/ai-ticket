from __future__ import annotations

import asyncio
from typing import Iterator

import httpx
import pytest

from ai_ticket.metrics import CONTENT_TYPE_LATEST
from ai_ticket.observability.metrics import MetricsStore
from ai_ticket.security import InMemoryRateLimiter
from ai_ticket.server import TOKEN_MANAGER, app
from ai_ticket import server
from ai_ticket.events.inference import CompletionResponse, ErrorResponse


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


@pytest.fixture(autouse=True)
def reset_auth_tokens() -> Iterator[None]:
    original_tokens = TOKEN_MANAGER.tokens
    yield
    TOKEN_MANAGER.update_tokens(original_tokens)


@pytest.mark.anyio("asyncio")
async def test_handle_event_success(mocker: pytest.MockFixture) -> None:
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = CompletionResponse(completion="Test completion")

    payload = {"content": "Test prompt"}
    async with _make_client() as client:
        response = await client.post("/event", json=payload)

    assert response.status_code == 200
    assert response.json() == {"completion": "Test completion"}
    mock_on_event.assert_called_once_with(payload)


@pytest.mark.anyio("asyncio")
async def test_handle_event_missing_content(mocker: pytest.MockFixture) -> None:
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = ErrorResponse(
        error="missing_content_field",
        message="The 'content' field is required.",
        status_code=400,
        details="'content' field is missing...",
    )

    payload = {"some_other_key": "some_value"}
    async with _make_client() as client:
        response = await client.post("/event", json=payload)

    assert response.status_code == 400
    assert response.json()["error"] == "missing_content_field"
    mock_on_event.assert_called_once_with(payload)


@pytest.mark.anyio("asyncio")
async def test_handle_event_not_json(mocker: pytest.MockFixture) -> None:
    mock_on_event = mocker.patch("ai_ticket.server.on_event")

    async with _make_client() as client:
        response = await client.post("/event", data="not a json string", headers={"Content-Type": "text/plain"})

    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "invalid_request"
    assert "Request must be JSON" in data["details"]
    mock_on_event.assert_not_called()


@pytest.mark.anyio("asyncio")
async def test_handle_event_on_event_error(mocker: pytest.MockFixture) -> None:
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = ErrorResponse(
        error="api_connection_error",
        message="Could not connect",
        status_code=503,
        details="Could not connect",
    )

    payload = {"content": "Test prompt for API error"}
    async with _make_client() as client:
        response = await client.post("/event", json=payload)

    assert response.status_code == 503
    assert response.json()["error"] == "api_connection_error"
    mock_on_event.assert_called_once_with(payload)


@pytest.mark.anyio("asyncio")
async def test_handle_event_prompt_extraction_failed(mocker: pytest.MockFixture) -> None:
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = ErrorResponse(
        error="prompt_extraction_failed",
        message="Could not derive prompt.",
        status_code=422,
        details="Could not derive prompt.",
    )

    payload = {"content": {"unexpected_structure": True}}
    async with _make_client() as client:
        response = await client.post("/event", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "prompt_extraction_failed"
    mock_on_event.assert_called_once_with(payload)


@pytest.mark.anyio("asyncio")
async def test_missing_authentication_token(mocker: pytest.MockFixture) -> None:
    mocker.patch("ai_ticket.server.on_event").return_value = CompletionResponse(completion="ok")
    TOKEN_MANAGER.update_tokens({"secret-token"})

    async with _make_client() as client:
        response = await client.post("/event", json={"content": "needs auth"})

    assert response.status_code == 401
    data = response.json()
    assert data["error"] == "unauthorised"


@pytest.mark.anyio("asyncio")
async def test_valid_bearer_token_allows_request(mocker: pytest.MockFixture) -> None:
    mocker.patch("ai_ticket.server.on_event").return_value = CompletionResponse(completion="secure")
    TOKEN_MANAGER.update_tokens({"secret-token"})

    async with _make_client() as client:
        response = await client.post(
            "/event",
            json={"content": "authorised"},
            headers={"Authorization": "Bearer secret-token"},
        )

    assert response.status_code == 200
    assert response.json()["completion"] == "secure"


@pytest.mark.anyio("asyncio")
async def test_metrics_endpoint_available() -> None:
    async with _make_client() as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST


@pytest.mark.anyio("asyncio")
async def test_rate_limiter_blocks_when_threshold_exceeded(mocker: pytest.MockFixture) -> None:
    mocker.patch("ai_ticket.server.on_event").return_value = CompletionResponse(completion="ok")
    original = server.RATE_LIMITER
    server.RATE_LIMITER = InMemoryRateLimiter(limit=1, window_seconds=60)

    try:
        async with _make_client() as client:
            first = await client.post(
                "/event", json={"content": "first"}, headers={"X-Forwarded-For": "1.1.1.1"}
            )
            assert first.status_code == 200

        async with _make_client() as client:
            second = await client.post(
                "/event", json={"content": "second"}, headers={"X-Forwarded-For": "1.1.1.1"}
            )
            assert second.status_code == 429
            data = second.json()
            assert data["error"] == "rate_limited"
    finally:
        server.RATE_LIMITER = original


@pytest.mark.anyio("asyncio")
async def test_metrics_stream_emits_updates(mocker: pytest.MockFixture) -> None:
    fresh_store = MetricsStore()
    mocker.patch("ai_ticket.server.metrics_store", fresh_store)

    stream = server._metrics_event_stream()
    stream_iter = stream.__aiter__()

    try:
        first_chunk = await asyncio.wait_for(stream_iter.__anext__(), timeout=1.0)
        assert first_chunk.startswith("data: ")

        fresh_store.record_event(latency_s=0.05, success=True)
        second_chunk = await asyncio.wait_for(stream_iter.__anext__(), timeout=1.0)
        assert '"successes": 1' in second_chunk
    finally:
        await stream_iter.aclose()
