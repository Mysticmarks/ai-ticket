from __future__ import annotations

from typing import Any

import httpx
import pytest

from ai_ticket.backends.kobold_client import KoboldCompletionResult, get_kobold_completion


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fast_sleep(attempt: int) -> None:  # pragma: no cover - trivial
        return None

    monkeypatch.setattr("ai_ticket.backends.kobold_client._sleep", _fast_sleep)


@pytest.fixture
def fake_async_client(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, list[Any]], list[tuple[str, dict[str, Any]]]]:
    script: dict[str, list[Any]] = {}
    calls: list[tuple[str, dict[str, Any]]] = []

    class _FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - simple wiring
            self.closed = False

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str] | None = None,
            json: dict[str, Any] | None = None,
            timeout: Any = None,
        ) -> httpx.Response:
            calls.append((url, json or {}))
            queue = script.get(url)
            if not queue:
                raise AssertionError(f"Unexpected call to {url}")
            result = queue.pop(0)
            if isinstance(result, Exception):
                raise result
            assert isinstance(result, httpx.Response)
            return result

        async def aclose(self) -> None:
            self.closed = True

    monkeypatch.setattr("ai_ticket.backends.pipeline.httpx.AsyncClient", _FakeClient)
    monkeypatch.setattr("ai_ticket.backends.kobold_client.httpx.AsyncClient", _FakeClient)

    return script, calls


def _response(url: str, *, status: int = 200, payload: dict[str, Any] | None = None, text: str | None = None) -> httpx.Response:
    request = httpx.Request("POST", url)
    if payload is not None:
        return httpx.Response(status, json=payload, request=request)
    assert text is not None
    return httpx.Response(status, content=text.encode(), request=request)


def test_get_kobold_completion_success_chat(fake_async_client: tuple[dict[str, list[Any]], list[tuple[str, dict[str, Any]]]]) -> None:
    script, calls = fake_async_client
    chat_url = "http://localhost:5001/api/v1/chat/completions"
    script[chat_url] = [
        _response(
            chat_url,
            payload={
                "choices": [
                    {"message": {"content": " Test completion "}},
                ]
            },
        )
    ]

    result = get_kobold_completion("Test prompt")

    assert isinstance(result, KoboldCompletionResult)
    assert result.completion == "Test completion"
    assert result.error is None
    assert calls[0][0] == chat_url
    assert calls[0][1]["messages"][0]["content"] == "Test prompt"


def test_get_kobold_completion_fallback(fake_async_client: tuple[dict[str, list[Any]], list[tuple[str, dict[str, Any]]]]) -> None:
    script, calls = fake_async_client
    chat_url = "http://localhost:5001/api/v1/chat/completions"
    completion_url = "http://localhost:5001/api/v1/completions"

    rate_limit_response = _response(chat_url, status=429, payload={"error": "rate limited"})
    script[chat_url] = [
        httpx.HTTPStatusError("rate limited", request=rate_limit_response.request, response=rate_limit_response),
        _response(
            chat_url,
            payload={
                "choices": [
                    {"message": {"content": "Fallback via chat"}},
                ]
            },
        ),
    ]
    script[completion_url] = [
        _response(
            completion_url,
            payload={
                "choices": [
                    {"text": "Plain fallback"},
                ]
            },
        )
    ]

    result = get_kobold_completion("Prompt needing fallback")

    assert result.is_success()
    assert result.completion == "Fallback via chat"
    assert len(calls) >= 2
    assert calls[0][0] == chat_url
    assert calls[1][0] == chat_url


def test_get_kobold_completion_all_fail(fake_async_client: tuple[dict[str, list[Any]], list[tuple[str, dict[str, Any]]]]) -> None:
    script, _ = fake_async_client
    chat_url = "http://localhost:5001/api/v1/chat/completions"
    completion_url = "http://localhost:5001/api/v1/completions"

    script[chat_url] = [httpx.RequestError("boom", request=httpx.Request("POST", chat_url))]
    script[completion_url] = [httpx.RequestError("boom", request=httpx.Request("POST", completion_url))]

    result = get_kobold_completion("Prompt failure")

    assert not result.is_success()
    assert result.error == "api_request_error"


def test_get_kobold_completion_custom_url(
    fake_async_client: tuple[dict[str, list[Any]], list[tuple[str, dict[str, Any]]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script, calls = fake_async_client
    custom_url = "http://mykobold.ai:1234/customapi"
    monkeypatch.setenv("KOBOLDCPP_API_URL", custom_url)

    chat_url = f"{custom_url}/v1/chat/completions"
    script[chat_url] = [
        _response(
            chat_url,
            payload={
                "choices": [
                    {"message": {"content": "Custom URL works"}},
                ]
            },
        )
    ]

    result = get_kobold_completion("Test prompt custom URL")

    assert result.is_success()
    assert calls[0][0] == chat_url

    monkeypatch.delenv("KOBOLDCPP_API_URL", raising=False)

