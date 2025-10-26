from __future__ import annotations

import asyncio
import json
import threading
from collections import defaultdict

import pytest
import requests

from ai_ticket.backends.kobold_client import async_get_kobold_completion


class FakePost:
    def __init__(self, script: dict[str, list[object]]):
        self._script = defaultdict(list, {url: list(events) for url, events in script.items()})
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, url: str, *, headers: dict[str, str], json: dict, timeout: int) -> requests.Response:
        with self._lock:
            self.calls.append(url)
            queue = self._script[url]
            if not queue:
                raise AssertionError(f"Unexpected call to {url}")
            result = queue.pop(0)
        if isinstance(result, Exception):
            raise result
        assert isinstance(result, requests.Response)
        return result


def _response(url: str, *, status_code: int = 200, json_data: dict | None = None, text: str | None = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response.url = url
    if json_data is not None:
        response._content = json.dumps(json_data).encode()
        response.headers["Content-Type"] = "application/json"
    else:
        assert text is not None
        response._content = text.encode()
    return response


def test_async_get_kobold_completion_success(monkeypatch: pytest.MonkeyPatch) -> None:
    base_url = "http://kobold.local"
    chat_url = f"{base_url}/v1/chat/completions"
    completion_url = f"{base_url}/v1/completions"

    script = {
        chat_url: [
            _response(
                chat_url,
                json_data={
                    "choices": [
                        {"message": {"content": "parallel success"}},
                    ]
                },
            )
        ],
        completion_url: [
            requests.exceptions.ConnectionError("boom"),
        ],
    }

    fake_post = FakePost(script)
    monkeypatch.setattr("ai_ticket.backends.kobold_client.requests.post", fake_post)

    result = asyncio.run(
        async_get_kobold_completion(
            "Tell me a story",
            kobold_url=base_url,
        )
    )

    assert result.is_success
    assert result.completion == "parallel success"
    assert chat_url in fake_post.calls


def test_async_get_kobold_completion_json_error(monkeypatch: pytest.MonkeyPatch) -> None:
    base_url = "http://kobold.local"
    chat_url = f"{base_url}/v1/chat/completions"
    completion_url = f"{base_url}/v1/completions"

    script = {
        chat_url: [
            _response(chat_url, text="not json"),
        ],
        completion_url: [
            _response(
                completion_url,
                json_data={
                    "choices": [
                        {"text": "fallback"},
                    ]
                },
            )
        ],
    }

    fake_post = FakePost(script)
    monkeypatch.setattr("ai_ticket.backends.kobold_client.requests.post", fake_post)

    result = asyncio.run(
        async_get_kobold_completion(
            "Tell me a story",
            kobold_url=base_url,
        )
    )

    assert result.is_success
    assert result.completion == "fallback"


def test_async_get_kobold_completion_rate_limit_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    base_url = "http://kobold.local"
    chat_url = f"{base_url}/v1/chat/completions"
    completion_url = f"{base_url}/v1/completions"

    rate_limit_response = _response(chat_url, status_code=429, json_data={"error": "rl"})

    script = {
        chat_url: [
            requests.exceptions.HTTPError("rate limit", response=rate_limit_response),
            _response(
                chat_url,
                json_data={
                    "choices": [
                        {"message": {"content": "second attempt"}},
                    ]
                },
            ),
        ],
        completion_url: [
            requests.exceptions.ConnectionError("unavailable") for _ in range(3)
        ],
    }

    fake_post = FakePost(script)
    monkeypatch.setattr("ai_ticket.backends.kobold_client.requests.post", fake_post)
    monkeypatch.setattr("ai_ticket.backends.kobold_client._sleep", lambda attempt: None)

    result = asyncio.run(
        async_get_kobold_completion(
            "Tell me a story",
            kobold_url=base_url,
        )
    )

    assert result.is_success
    assert result.completion == "second attempt"
    assert fake_post.calls.count(chat_url) == 2
