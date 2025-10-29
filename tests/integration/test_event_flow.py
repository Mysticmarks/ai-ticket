from __future__ import annotations

import json
from pathlib import Path

import pytest
import httpx

from ai_ticket.backends.kobold_client import KoboldCompletionResult
from ai_ticket.server import app

_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "events"


def _load_message_payload(index: int = 0) -> tuple[dict[str, object], str]:
    messages = json.loads((_DATA_DIR / "chat_messages.json").read_text())
    payload = messages[index]
    user_prompt = next(
        message["content"]
        for message in reversed(payload["messages"])
        if message.get("role") == "user"
    )
    return {"content": json.dumps(payload)}, user_prompt


@pytest.fixture(scope="module")
def asgi_transport() -> httpx.ASGITransport:
    return httpx.ASGITransport(app=app)


@pytest.fixture
def chat_completion_event() -> tuple[dict[str, object], str]:
    return _load_message_payload(0)


@pytest.fixture
def incident_event() -> tuple[dict[str, object], str]:
    return _load_message_payload(1)


@pytest.mark.anyio("asyncio")
async def test_event_flow_success(
    asgi_transport: httpx.ASGITransport,
    chat_completion_event: tuple[dict[str, object], str],
    mocker: pytest.MockFixture,
) -> None:
    event_payload, expected_prompt = chat_completion_event
    backend_calls: list[str] = []

    def _fake_backend(prompt: str) -> KoboldCompletionResult:
        backend_calls.append(prompt)
        return KoboldCompletionResult(completion=f"Echo: {prompt}")

    mocker.patch("ai_ticket.events.inference.get_kobold_completion", side_effect=_fake_backend)

    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as httpx_client:
        response = await httpx_client.post("/event", json=event_payload)

    assert response.status_code == 200
    body = response.json()
    assert body == {"completion": f"Echo: {expected_prompt}"}
    assert backend_calls == [expected_prompt]


@pytest.mark.anyio("asyncio")
async def test_event_flow_backend_error(
    asgi_transport: httpx.ASGITransport,
    incident_event: tuple[dict[str, object], str],
    mocker: pytest.MockFixture,
) -> None:
    event_payload, expected_prompt = incident_event

    mock_backend = mocker.patch(
        "ai_ticket.events.inference.get_kobold_completion",
        return_value=KoboldCompletionResult(error="backend_failure", details="timeout"),
    )

    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as httpx_client:
        response = await httpx_client.post("/event", json=event_payload)

    assert response.status_code == 502
    body = response.json()
    assert body["error"] == "backend_failure"
    assert body["details"] == "timeout"
    assert body["message"] == "Failed to retrieve completion from backend."
    mock_backend.assert_called_once_with(prompt=expected_prompt)
