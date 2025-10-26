import asyncio
import json
from typing import Iterable
from unittest.mock import Mock

import pytest
import requests

from ai_ticket.backends.kobold_client import (
    KoboldChatClient,
    KoboldCompletionClient,
    InvalidResponseError,
    NonRetryableHTTPError,
    RequestFailureError,
    RetryConfig,
    get_kobold_completion,
)


def make_response(
    status_code: int,
    *,
    json_data: dict | None = None,
    text: str = "",
    headers: dict | None = None,
    stream_chunks: Iterable[str] | None = None,
):
    response = Mock(spec=requests.Response)
    response.status_code = status_code
    response.text = text
    response.headers = headers or {}
    response.url = "http://kobold/api"
    if json_data is not None:
        response.json.return_value = json_data
    else:
        response.json.side_effect = json.JSONDecodeError("msg", "", 0)
    if stream_chunks is None:
        response.iter_lines.return_value = []
    else:
        response.iter_lines.return_value = list(stream_chunks)
    response.close.return_value = None
    return response


@pytest.fixture
def retry_config():
    return RetryConfig(max_attempts=3, sleep=lambda _: None)


def test_chat_client_complete_success(retry_config):
    session = Mock(spec=requests.Session)
    response = make_response(
        200,
        json_data={"choices": [{"message": {"content": " Hello world "}}]},
    )
    session.post.return_value = response

    client = KoboldChatClient("http://localhost:5001/api", session=session, retry_config=retry_config)
    result = client.complete("Say hello")
    assert result == "Hello world"
    session.post.assert_called_once()


def test_completion_client_streaming_success(retry_config):
    session = Mock(spec=requests.Session)
    response = make_response(
        200,
        json_data={"choices": [{"text": "unused"}]},
        stream_chunks=[
            "data: {\"choices\":[{\"text\":\"Hello\"}]}",
            "data: {\"choices\":[{\"text\":\" world\"}]}",
            "data: [DONE]",
        ],
    )
    session.post.return_value = response

    client = KoboldCompletionClient("http://localhost:5001/api", session=session, retry_config=retry_config)
    pieces = list(client.stream("Hi"))
    assert pieces == ["Hello", " world"]


def test_async_chat_stream(retry_config):
    session = Mock(spec=requests.Session)
    response = make_response(
        200,
        json_data={"choices": [{"message": {"content": "ignored"}}]},
        stream_chunks=[
            "data: {\"choices\":[{\"delta\":{\"content\":\"Chunk\"}}]}",
            "data: {\"choices\":[{\"delta\":{\"content\":\" two\"}}]}",
            "data: [DONE]",
        ],
    )
    session.post.return_value = response

    client = KoboldChatClient("http://localhost:5001/api", session=session, retry_config=retry_config)

    async def collect() -> list[str]:
        chunks = []
        async for chunk in client.astream("prompt"):
            chunks.append(chunk)
        return chunks

    collected = asyncio.run(collect())
    assert collected == ["Chunk", " two"]


def test_invalid_response_raises(retry_config):
    session = Mock(spec=requests.Session)
    response = make_response(200, json_data=None, text="not-json")
    session.post.return_value = response

    client = KoboldChatClient("http://localhost:5001/api", session=session, retry_config=retry_config)
    with pytest.raises(InvalidResponseError):
        client.complete("prompt")


def test_non_retryable_client_error(retry_config):
    session = Mock(spec=requests.Session)
    response = make_response(403, json_data={"error": "Forbidden"}, text="Forbidden")
    session.post.return_value = response

    client = KoboldChatClient("http://localhost:5001/api", session=session, retry_config=retry_config)
    with pytest.raises(NonRetryableHTTPError):
        client.complete("prompt")


def test_retry_on_server_error_then_success(retry_config):
    session = Mock(spec=requests.Session)
    server_error = make_response(500, json_data={"error": "boom"}, text="boom")
    success = make_response(
        200,
        json_data={"choices": [{"message": {"content": "ok"}}]},
    )
    session.post.side_effect = [server_error, success]

    client = KoboldChatClient("http://localhost:5001/api", session=session, retry_config=retry_config)
    assert client.complete("prompt") == "ok"
    assert session.post.call_count == 2


def test_retry_after_header_used(retry_config):
    session = Mock(spec=requests.Session)
    rate_limited = make_response(429, json_data={"error": "rate"}, headers={"Retry-After": "0"})
    success = make_response(
        200,
        json_data={"choices": [{"message": {"content": "ok"}}]},
    )
    session.post.side_effect = [rate_limited, success]

    client = KoboldChatClient("http://localhost:5001/api", session=session, retry_config=retry_config)
    assert client.complete("prompt") == "ok"
    assert session.post.call_count == 2


def test_transport_error_wrapped(retry_config):
    session = Mock(spec=requests.Session)
    session.post.side_effect = requests.exceptions.RequestException("boom")

    client = KoboldChatClient("http://localhost:5001/api", session=session, retry_config=retry_config)
    with pytest.raises(RequestFailureError):
        client.complete("prompt")


def test_get_kobold_completion_fallback(monkeypatch):
    server_error = make_response(500, json_data={"error": "boom"}, text="boom")
    success = make_response(200, json_data={"choices": [{"text": "fallback"}]})

    post = Mock()
    post.side_effect = [server_error, server_error, success]
    monkeypatch.setattr(requests.Session, "post", post)

    result = get_kobold_completion("prompt", retry_config=RetryConfig(max_attempts=2, sleep=lambda _: None))
    assert result == {"completion": "fallback"}
    assert post.call_count == 3


def test_get_kobold_completion_failure(monkeypatch):
    server_error = make_response(500, json_data={"error": "boom"}, text="boom")
    client_error = make_response(400, json_data={"error": "bad"}, text="bad")

    post = Mock()
    post.side_effect = [server_error, server_error, client_error]
    monkeypatch.setattr(requests.Session, "post", post)

    result = get_kobold_completion("prompt", retry_config=RetryConfig(max_attempts=2, sleep=lambda _: None))
    assert result["error"] == "completion_failure"
    assert post.call_count == 3


def test_retryable_transport_error_then_success(retry_config):
    session = Mock(spec=requests.Session)
    timeout = requests.exceptions.Timeout("timeout")
    success = make_response(200, json_data={"choices": [{"message": {"content": "ok"}}]})
    session.post.side_effect = [timeout, success]

    client = KoboldChatClient("http://localhost:5001/api", session=session, retry_config=retry_config)
    assert client.complete("prompt") == "ok"
    assert session.post.call_count == 2
