from __future__ import annotations

import anyio
import pytest
from collections.abc import AsyncIterator, Iterator

import ai_ticket.server as server
from ai_ticket.events.inference import CompletionResponse, ErrorResponse
from ai_ticket.metrics import CONTENT_TYPE_LATEST
from ai_ticket.observability.metrics import MetricsStore
from ai_ticket.security import InMemoryRateLimiter
from httpx import ASGITransport, AsyncClient


pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    lifespan_manager = None
    router = getattr(server.app, "router", None)
    if router is not None and hasattr(router, "lifespan_context"):
        lifespan_manager = router.lifespan_context(server.app)
        await lifespan_manager.__aenter__()

    try:
        transport = ASGITransport(app=server.app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client
    finally:
        if lifespan_manager is not None:
            await lifespan_manager.__aexit__(None, None, None)


@pytest.fixture(autouse=True)
def reset_auth_tokens() -> Iterator[None]:
    original_tokens = server.TOKEN_MANAGER.tokens
    yield
    server.TOKEN_MANAGER.update_tokens(original_tokens)


async def test_handle_event_success(client: AsyncClient, mocker) -> None:
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = CompletionResponse(completion="Test completion")

    payload = {"content": {"prompt": "Test prompt"}}
    response = await client.post("/event", json=payload)

    assert response.status_code == 200
    assert response.json() == {"completion": "Test completion"}
    mock_on_event.assert_called_once_with(payload)


async def test_handle_event_missing_content(client: AsyncClient, mocker) -> None:
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = ErrorResponse(
        error="missing_content_field",
        message="The 'content' field is required.",
        status_code=400,
        details="'content' field is missing...",
    )

    payload = {"some_other_key": "some_value"}
    response = await client.post("/event", json=payload)

    assert response.status_code == 400
    assert response.json()["error"] == "missing_content_field"
    mock_on_event.assert_called_once_with(payload)


async def test_handle_event_not_json(client: AsyncClient, mocker) -> None:
    mock_on_event = mocker.patch("ai_ticket.server.on_event")

    response = await client.post(
        "/event",
        content="not a json string",
        headers={"Content-Type": "text/plain"},
    )

    assert response.status_code == 400
    response_data = response.json()
    assert response_data["error"] == "invalid_request"
    assert "Request must be JSON" in response_data["details"]
    mock_on_event.assert_not_called()


async def test_handle_event_on_event_error(client: AsyncClient, mocker) -> None:
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = ErrorResponse(
        error="api_connection_error",
        message="Could not connect",
        status_code=503,
        details="Could not connect",
    )

    payload = {"content": {"prompt": "Test prompt for API error"}}
    response = await client.post("/event", json=payload)

    assert response.status_code == 503
    assert response.json()["error"] == "api_connection_error"
    mock_on_event.assert_called_once_with(payload)


async def test_handle_event_prompt_extraction_failed(client: AsyncClient, mocker) -> None:
    mock_on_event = mocker.patch("ai_ticket.server.on_event")
    mock_on_event.return_value = ErrorResponse(
        error="prompt_extraction_failed",
        message="Could not derive prompt.",
        status_code=422,
        details="Could not derive prompt.",
    )

    payload = {"content": {"unexpected_structure": True}}
    response = await client.post("/event", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "prompt_extraction_failed"
    mock_on_event.assert_called_once_with(payload)


@pytest.mark.failure_mode
async def test_missing_authentication_token(client: AsyncClient, mocker) -> None:
    mocker.patch("ai_ticket.server.on_event").return_value = CompletionResponse(completion="ok")
    server.TOKEN_MANAGER.update_tokens({"secret-token"})

    response = await client.post("/event", json={"content": {"prompt": "needs auth"}})

    assert response.status_code == 401
    data = response.json()
    assert data["error"] == "unauthorised"


@pytest.mark.failure_mode
async def test_invalid_bearer_token_rejected(client: AsyncClient, mocker) -> None:
    mocker.patch("ai_ticket.server.on_event").return_value = CompletionResponse(completion="ok")
    server.TOKEN_MANAGER.update_tokens({"secret-token"})

    response = await client.post(
        "/event",
        json={"content": {"prompt": "authorised"}},
        headers={"Authorization": "Bearer totally-wrong"},
    )

    assert response.status_code == 403
    data = response.json()
    assert data["error"] == "forbidden"
    assert "Invalid authentication token" in data["details"]


async def test_valid_bearer_token_allows_request(client: AsyncClient, mocker) -> None:
    mocker.patch("ai_ticket.server.on_event").return_value = CompletionResponse(completion="secure")
    server.TOKEN_MANAGER.update_tokens({"secret-token"})

    response = await client.post(
        "/event",
        json={"content": {"prompt": "authorised"}},
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 200
    assert response.json()["completion"] == "secure"


async def test_metrics_endpoint_available(client: AsyncClient) -> None:
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST


@pytest.mark.failure_mode
async def test_rate_limiter_blocks_when_threshold_exceeded(client: AsyncClient, mocker) -> None:
    mocker.patch("ai_ticket.server.on_event").return_value = CompletionResponse(completion="ok")
    original = server.RATE_LIMITER
    server.RATE_LIMITER = InMemoryRateLimiter(limit=1, window_seconds=60)

    try:
        first = await client.post(
            "/event",
            json={"content": {"prompt": "first"}},
            headers={"X-Forwarded-For": "1.1.1.1"},
        )
        assert first.status_code == 200

        second = await client.post(
            "/event",
            json={"content": {"prompt": "second"}},
            headers={"X-Forwarded-For": "1.1.1.1"},
        )
        assert second.status_code == 429
        data = second.json()
        assert data["error"] == "rate_limited"
        retry_after = second.headers.get("Retry-After")
        assert retry_after is not None
        assert int(retry_after) >= 0
    finally:
        server.RATE_LIMITER = original


async def test_metrics_stream_emits_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    fresh_store = MetricsStore()
    monkeypatch.setattr(server, "metrics_store", fresh_store)

    stream = server._metrics_event_stream()
    first_chunk = await stream.__anext__()
    assert first_chunk.startswith("data: ")
    assert len(fresh_store._subscribers) == 1

    fresh_store.record_event(latency_s=0.05, success=True)
    second_chunk = await stream.__anext__()
    assert '"successes": 1' in second_chunk

    await stream.aclose()

@pytest.mark.failure_mode
async def test_metrics_stream_reconnects_after_client_drop(monkeypatch: pytest.MonkeyPatch) -> None:
    fresh_store = MetricsStore()
    monkeypatch.setattr(server, "metrics_store", fresh_store)

    first_stream = server._metrics_event_stream()
    await first_stream.__anext__()
    assert len(fresh_store._subscribers) == 1

    await first_stream.aclose()

    async def _wait_for_unsubscribe(timeout: float = 0.5) -> bool:
        deadline = anyio.current_time() + timeout
        while anyio.current_time() < deadline:
            if not fresh_store._subscribers:
                return True
            await anyio.sleep(0.01)
        return not fresh_store._subscribers

    assert await _wait_for_unsubscribe()

    second_stream = server._metrics_event_stream()
    await second_stream.__anext__()

    fresh_store.record_event(
        latency_s=0.02,
        success=False,
        error_code="rate_limited",
        message="burst",
    )
    follow_up = await second_stream.__anext__()
    assert '"rate_limited"' in follow_up

    await second_stream.aclose()

    assert await _wait_for_unsubscribe()
