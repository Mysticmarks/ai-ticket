from __future__ import annotations

from typing import Any

import pytest

from ai_ticket._compat import anyio, httpx

from ai_ticket.backends.kobold_client import KoboldCompletionResult, async_get_kobold_completion


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fast_sleep(attempt: int) -> None:  # pragma: no cover - trivial
        return None

    monkeypatch.setattr("ai_ticket.backends.kobold_client._sleep", _fast_sleep)


@pytest.fixture
def fake_async_client(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, list[Any]], list[str]]:
    script: dict[str, list[Any]] = {}
    calls: list[str] = []

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
            calls.append(url)
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


def test_async_get_kobold_completion_success(fake_async_client: tuple[dict[str, list[Any]], list[str]]) -> None:
    script, calls = fake_async_client
    base_url = "http://kobold.local"
    chat_url = f"{base_url}/v1/chat/completions"
    script[chat_url] = [
        _response(
            chat_url,
            payload={
                "choices": [
                    {"message": {"content": "parallel success"}},
                ]
            },
        )
    ]

    result = anyio.run(
        async_get_kobold_completion,
        "Tell me a story",
        base_url,
    )

    assert isinstance(result, KoboldCompletionResult)
    assert result.is_success()
    assert result.completion == "parallel success"
    assert calls == [chat_url]


def test_async_get_kobold_completion_json_error(fake_async_client: tuple[dict[str, list[Any]], list[str]]) -> None:
    script, _ = fake_async_client
    base_url = "http://kobold.local"
    chat_url = f"{base_url}/v1/chat/completions"
    completion_url = f"{base_url}/v1/completions"

    script[chat_url] = [_response(chat_url, text="not json")]
    script[completion_url] = [
        _response(
            completion_url,
            payload={
                "choices": [
                    {"text": "fallback"},
                ]
            },
        )
    ]

    result = anyio.run(
        async_get_kobold_completion,
        "Tell me a story",
        base_url,
    )

    assert result.is_success()
    assert result.completion == "fallback"


def test_async_get_kobold_completion_rate_limit(fake_async_client: tuple[dict[str, list[Any]], list[str]]) -> None:
    script, calls = fake_async_client
    base_url = "http://kobold.local"
    chat_url = f"{base_url}/v1/chat/completions"
    completion_url = f"{base_url}/v1/completions"

    rate_limit_response = _response(chat_url, status=429, payload={"error": "rl"})
    script[chat_url] = [
        httpx.HTTPStatusError("rate limited", request=rate_limit_response.request, response=rate_limit_response),
        _response(
            chat_url,
            payload={
                "choices": [
                    {"message": {"content": "second attempt"}},
                ]
            },
        ),
    ]
    script[completion_url] = [
        httpx.ConnectError("boom", request=httpx.Request("POST", completion_url))
    ]

    result = anyio.run(
        async_get_kobold_completion,
        "Tell me a story",
        base_url,
    )

    assert result.is_success()
    assert result.completion == "second attempt"
    assert calls.count(chat_url) == 2

