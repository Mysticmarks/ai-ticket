"""Client utilities for interacting with a KoboldCPP-compatible API.

This module exposes composable chat and completion clients that share a
robust request pipeline featuring configurable retry/backoff logic.  Both
streaming and asynchronous helpers are available for high-throughput
scenarios, while the legacy :func:`get_kobold_completion` helper provides a
simple string-based interface for existing callers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from contextlib import closing
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Callable, Dict, Generator, Optional, TypeVar

import requests

DEFAULT_KOBOLDCPP_API_URL = "http://localhost:5001/api"

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry/backoff behaviour."""

    max_attempts: int = 3
    initial_delay: float = 0.5
    max_delay: float = 10.0
    backoff_multiplier: float = 2.0
    timeout: int = 120
    sleep: Callable[[float], None] = time.sleep


class KoboldAPIError(RuntimeError):
    """Base error raised for Kobold client failures."""


class RetryableRequestError(KoboldAPIError):
    """Raised when a request fails due to retryable transport issues."""


class RequestFailureError(KoboldAPIError):
    """Raised when a request fails due to a non-retryable transport issue."""


class RetryableHTTPError(KoboldAPIError):
    """Raised when the API responds with a retryable HTTP error."""

    def __init__(self, response: requests.Response):
        self.response = response
        super().__init__(self._format_message(response))

    @staticmethod
    def _format_message(response: requests.Response) -> str:
        body = (response.text or "")[:200]
        return f"HTTP {response.status_code} response from {response.url}: {body}"


class RetryAfterError(RetryableHTTPError):
    """Retryable HTTP error that conveys an explicit retry-after delay."""

    def __init__(self, response: requests.Response, wait_time: Optional[float]):
        super().__init__(response)
        self.wait_time = wait_time


class NonRetryableHTTPError(KoboldAPIError):
    """Raised when the API responds with a non-retryable HTTP error."""

    def __init__(self, response: requests.Response):
        self.response = response
        super().__init__(self._format_message(response))

    @staticmethod
    def _format_message(response: requests.Response) -> str:
        body = (response.text or "")[:200]
        return f"HTTP {response.status_code} response from {response.url}: {body}"


class InvalidResponseError(KoboldAPIError):
    """Raised when the API returns JSON that cannot be interpreted."""


class ConfigurationError(KoboldAPIError):
    """Raised when the client cannot be configured correctly."""


def _parse_retry_after(header_value: Optional[str]) -> Optional[float]:
    if not header_value:
        return None
    try:
        return float(header_value)
    except (TypeError, ValueError):
        return None

class _RetryController:
    """Simple retry manager implementing exponential backoff."""

    def __init__(self, config: RetryConfig) -> None:
        self.config = config

    def _calculate_wait(self, attempt: int) -> float:
        delay = self.config.initial_delay * (self.config.backoff_multiplier ** (attempt - 1))
        return min(delay, self.config.max_delay)

    def run(self, func: Callable[[], T]) -> T:
        last_exception: Optional[Exception] = None
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                return func()
            except RetryAfterError as exc:
                last_exception = exc
                if attempt >= self.config.max_attempts:
                    raise
                wait_time = exc.wait_time if exc.wait_time is not None else self._calculate_wait(attempt)
                logger.warning(
                    "Rate limited by KoboldCPP (attempt %s/%s). Retrying in %.2f seconds.",
                    attempt,
                    self.config.max_attempts,
                    wait_time,
                )
                self.config.sleep(wait_time)
            except (RetryableHTTPError, RetryableRequestError) as exc:
                last_exception = exc
                if attempt >= self.config.max_attempts:
                    raise
                wait_time = self._calculate_wait(attempt)
                logger.warning(
                    "Retryable error contacting KoboldCPP (attempt %s/%s): %s. Retrying in %.2f seconds.",
                    attempt,
                    self.config.max_attempts,
                    exc,
                    wait_time,
                )
                self.config.sleep(wait_time)
        if last_exception:
            raise last_exception
        raise RuntimeError("Retry controller exhausted without raising an error")


class BaseKoboldClient:
    """Shared functionality for Kobold chat and completion clients."""

    endpoint_path: str

    def __init__(
        self,
        base_url: Optional[str] = None,
        *,
        session: Optional[requests.Session] = None,
        retry_config: Optional[RetryConfig] = None,
    ) -> None:
        resolved_url = base_url or os.getenv("KOBOLDCPP_API_URL") or DEFAULT_KOBOLDCPP_API_URL
        if not resolved_url:
            raise ConfigurationError("KoboldCPP base URL is not configured")
        self.base_url = resolved_url.rstrip("/")
        self.session = session or requests.Session()
        self.retry_config = retry_config or RetryConfig()
        self._retry_controller = _RetryController(self.retry_config)

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------
    def _post(self, payload: Dict[str, Any], *, stream: bool = False) -> requests.Response:
        url = f"{self.base_url}{self.endpoint_path}"
        headers = {"Content-Type": "application/json"}
        logger.debug("POST %s payload keys: %s", url, list(payload.keys()))
        try:
            response = self.session.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.retry_config.timeout,
                stream=stream,
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            raise RetryableRequestError(str(exc)) from exc
        except requests.exceptions.RequestException as exc:
            raise RequestFailureError(str(exc)) from exc

        status = response.status_code
        if status == 429:
            wait_time = _parse_retry_after(response.headers.get("Retry-After"))
            logger.warning("Rate limit encountered for %s; retrying in %s seconds", url, wait_time)
            raise RetryAfterError(response, wait_time)
        if 500 <= status < 600:
            logger.warning("Server error %s from %s", status, url)
            raise RetryableHTTPError(response)
        if 400 <= status < 500:
            logger.error("Client error %s from %s", status, url)
            raise NonRetryableHTTPError(response)

        return response

    def _request_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        def _call() -> Dict[str, Any]:
            response = self._post(payload)
            with closing(response):
                try:
                    return response.json()
                except json.JSONDecodeError as exc:
                    raise InvalidResponseError(
                        f"Failed to decode JSON from {response.url}: {response.text[:200]}"
                    ) from exc

        return self._retry_controller.run(_call)

    def _stream(self, payload: Dict[str, Any], parser: Callable[[Any], Optional[str]]) -> Generator[str, None, None]:
        def _generator() -> Generator[str, None, None]:
            response = self._retry_controller.run(lambda: self._post(payload, stream=True))
            with closing(response):
                for raw_line in response.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    cleaned = raw_line.strip()
                    if not cleaned or cleaned in {"[DONE]", "data: [DONE]"}:
                        continue
                    if cleaned.startswith("data:"):
                        cleaned = cleaned[5:].strip()
                    try:
                        parsed = json.loads(cleaned)
                    except json.JSONDecodeError:
                        parsed = cleaned
                    piece = parser(parsed)
                    if piece:
                        yield piece

        return _generator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build_payload(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        top_p: float,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def parse_response(self, data: Dict[str, Any]) -> str:
        raise NotImplementedError

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 150,
        temperature: float = 0.7,
        top_p: float = 1.0,
    ) -> str:
        payload = self.build_payload(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        data = self._request_json(payload)
        return self.parse_response(data).strip()

    def stream(
        self,
        prompt: str,
        *,
        max_tokens: int = 150,
        temperature: float = 0.7,
        top_p: float = 1.0,
    ) -> Generator[str, None, None]:
        payload = self.build_payload(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        return self._stream(payload, self.parse_stream_chunk)

    async def acomplete(self, *args: Any, **kwargs: Any) -> str:
        return await asyncio.to_thread(self.complete, *args, **kwargs)

    async def astream(self, *args: Any, **kwargs: Any) -> AsyncGenerator[str, None]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Optional[str] | Exception] = asyncio.Queue()
        sentinel = object()

        def _producer() -> None:
            try:
                for chunk in self.stream(*args, **kwargs):
                    asyncio.run_coroutine_threadsafe(queue.put(chunk), loop).result()
            except Exception as exc:  # pragma: no cover - exercised in tests via controlled failure
                asyncio.run_coroutine_threadsafe(queue.put(exc), loop).result()
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(sentinel), loop).result()

        threading.Thread(target=_producer, daemon=True).start()

        while True:
            item = await queue.get()
            if item is sentinel:
                break
            if isinstance(item, Exception):
                raise item
            yield item  # type: ignore[misc]

    def parse_stream_chunk(self, chunk: Any) -> Optional[str]:
        raise NotImplementedError


class KoboldChatClient(BaseKoboldClient):
    endpoint_path = "/v1/chat/completions"

    def build_payload(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        top_p: float,
    ) -> Dict[str, Any]:
        return {
            "model": "koboldcpp-model",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }

    def parse_response(self, data: Dict[str, Any]) -> str:
        try:
            choices = data["choices"]
            message = choices[0]["message"]
            content = message["content"]
            return str(content)
        except (KeyError, IndexError, TypeError) as exc:
            raise InvalidResponseError(
                "Unexpected response structure for chat completion"
            ) from exc

    def parse_stream_chunk(self, chunk: Any) -> Optional[str]:
        if isinstance(chunk, str):
            return chunk
        try:
            choices = chunk.get("choices") or []
            if not choices:
                return None
            delta = choices[0].get("delta") or {}
            if "content" in delta:
                return str(delta["content"])
            message = choices[0].get("message") or {}
            if "content" in message:
                return str(message["content"])
        except (AttributeError, IndexError, TypeError):
            return None
        return None


class KoboldCompletionClient(BaseKoboldClient):
    endpoint_path = "/v1/completions"

    def build_payload(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        top_p: float,
    ) -> Dict[str, Any]:
        return {
            "model": "koboldcpp-model",
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }

    def parse_response(self, data: Dict[str, Any]) -> str:
        try:
            choices = data["choices"]
            text = choices[0]["text"]
            return str(text)
        except (KeyError, IndexError, TypeError) as exc:
            raise InvalidResponseError(
                "Unexpected response structure for plain completion"
            ) from exc

    def parse_stream_chunk(self, chunk: Any) -> Optional[str]:
        if isinstance(chunk, str):
            return chunk
        try:
            choices = chunk.get("choices") or []
            if not choices:
                return None
            text = choices[0].get("text")
            if text is not None:
                return str(text)
        except (AttributeError, IndexError, TypeError):
            return None
        return None


def get_kobold_completion(
    prompt: str,
    *,
    kobold_url: Optional[str] = None,
    max_length: int = 150,
    temperature: float = 0.7,
    top_p: float = 1.0,
    retry_config: Optional[RetryConfig] = None,
) -> Dict[str, str]:
    """Convenience helper that prefers the chat endpoint with plain fallback."""

    try:
        chat_client = KoboldChatClient(kobold_url, retry_config=retry_config)
        completion = chat_client.complete(
            prompt,
            max_tokens=max_length,
            temperature=temperature,
            top_p=top_p,
        )
        return {"completion": completion}
    except KoboldAPIError as chat_error:
        logger.warning("Chat completions failed: %s", chat_error)
    except Exception as chat_error:  # pragma: no cover - defensive logging of unexpected failures
        logger.exception("Unexpected chat completion failure: %s", chat_error)
        return {"error": "chat_completion_failure", "details": str(chat_error)}

    try:
        completion_client = KoboldCompletionClient(kobold_url, retry_config=retry_config)
        completion = completion_client.complete(
            prompt,
            max_tokens=max_length,
            temperature=temperature,
            top_p=top_p,
        )
        return {"completion": completion}
    except KoboldAPIError as completion_error:
        logger.error("Completion endpoint failed: %s", completion_error)
        return {"error": "completion_failure", "details": str(completion_error)}
    except Exception as completion_error:  # pragma: no cover - defensive logging
        logger.exception("Unexpected completion failure: %s", completion_error)
        return {"error": "completion_failure", "details": str(completion_error)}
