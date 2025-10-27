"""KoboldCPP backend built on the generic pipeline interfaces."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Final

import anyio
import httpx

from .base import (
    AsyncBackend,
    BackendContext,
    CompletionRequest,
    CompletionResult,
    StreamingNotSupported,
)
from .pipeline import BackendPipeline, BackendSlotConfig


logger = logging.getLogger(__name__)


DEFAULT_KOBOLDCPP_API_URL: Final[str] = "http://localhost:5001/api"
MAX_RETRIES: Final[int] = 3
_BACKOFF_SECONDS: Final[tuple[float, ...]] = (0.1, 0.25, 0.5)
_TRANSIENT_ERRORS: Final[frozenset[str]] = frozenset(
    {
        "api_connection_error",
        "api_server_error",
        "api_rate_limited",
        "api_request_error",
        "api_response_format_error",
        "api_response_structure_error",
    }
)


@dataclass(frozen=True)
class KoboldEndpoint:
    name: str
    path: str
    payload_builder: Callable[[CompletionRequest], dict[str, Any]]
    extractor: Callable[[dict[str, Any]], str | None]


def _chat_payload(request: CompletionRequest) -> dict[str, Any]:
    return {
        "model": "koboldcpp-model",
        "messages": [{"role": "user", "content": request.prompt}],
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
        "top_p": request.top_p,
    }


def _chat_extractor(data: dict[str, Any]) -> str | None:
    try:
        message = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(message, str):
        return None
    return message.strip()


def _completion_payload(request: CompletionRequest) -> dict[str, Any]:
    return {
        "model": "koboldcpp-model",
        "prompt": request.prompt,
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
        "top_p": request.top_p,
    }


def _completion_extractor(data: dict[str, Any]) -> str | None:
    try:
        text = data["choices"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(text, str):
        return None
    return text.strip()


_ENDPOINTS: Final[tuple[KoboldEndpoint, ...]] = (
    KoboldEndpoint(
        name="chat",
        path="/v1/chat/completions",
        payload_builder=_chat_payload,
        extractor=_chat_extractor,
    ),
    KoboldEndpoint(
        name="completion",
        path="/v1/completions",
        payload_builder=_completion_payload,
        extractor=_completion_extractor,
    ),
)


KoboldCompletionResult = CompletionResult


class KoboldBackend(AsyncBackend):
    """Async backend implementation targeting a KoboldCPP compatible API."""

    def __init__(
        self,
        *,
        base_url: str,
        endpoints: tuple[KoboldEndpoint, ...] = _ENDPOINTS,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._endpoints = endpoints
        self._max_retries = max_retries

    @property
    def name(self) -> str:
        return "koboldcpp"

    async def acomplete(
        self,
        request: CompletionRequest,
        *,
        context: BackendContext | None = None,
    ) -> CompletionResult:
        if not self._base_url:
            logger.error("KoboldCPP base URL is missing.")
            return CompletionResult(
                error="configuration_error",
                details="KOBOLDCPP_API_URL is not configured.",
            )

        client, cleanup = self._resolve_client(context)
        headers = {"Content-Type": "application/json"}
        errors: list[CompletionResult] = []

        try:
            for endpoint in self._endpoints:
                result = await self._fetch_from_endpoint(client, endpoint, request, headers)
                if result.is_success():
                    return result
                errors.append(result)
                if result.error not in _TRANSIENT_ERRORS:
                    return result
        finally:
            await cleanup()

        return _choose_error(
            errors,
            default_detail="All attempts to contact KoboldCPP API failed.",
        )

    async def astream(
        self,
        request: CompletionRequest,
        *,
        context: BackendContext | None = None,
    ):
        raise StreamingNotSupported("KoboldCPP backend does not support streaming yet.")

    def _resolve_client(
        self, context: BackendContext | None
    ) -> tuple[httpx.AsyncClient, Callable[[], Awaitable[None]]]:
        if context and isinstance(context.client, httpx.AsyncClient):
            async def _noop() -> None:
                await anyio.lowlevel.checkpoint()

            return context.client, _noop

        client = httpx.AsyncClient()

        async def _cleanup() -> None:
            await client.aclose()

        return client, _cleanup

    async def _fetch_from_endpoint(
        self,
        client: httpx.AsyncClient,
        endpoint: KoboldEndpoint,
        request: CompletionRequest,
        headers: dict[str, str],
    ) -> CompletionResult:
        last_error: CompletionResult | None = None

        for attempt in range(1, self._max_retries + 1):
            logger.info(
                "Attempting KoboldCPP %s endpoint",
                endpoint.name,
                extra={"url": f"{self._base_url}{endpoint.path}", "attempt": attempt},
            )

            try:
                response = await client.post(
                    f"{self._base_url}{endpoint.path}",
                    headers=headers,
                    json=endpoint.payload_builder(request),
                    timeout=None,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                logger.warning(
                    "HTTP error from KoboldCPP %s endpoint",
                    endpoint.name,
                    extra={"status_code": status_code, "attempt": attempt},
                )

                if status_code in {401, 403}:
                    return CompletionResult(
                        error="api_authentication_error",
                        details=_build_http_error_detail(endpoint.name, exc),
                    )

                if status_code == 429:
                    last_error = CompletionResult(
                        error="api_rate_limited",
                        details=_build_http_error_detail(endpoint.name, exc),
                    )
                    await _sleep(attempt)
                    continue

                if status_code is not None and 400 <= status_code < 500:
                    return CompletionResult(
                        error="api_client_error",
                        details=_build_http_error_detail(endpoint.name, exc),
                    )

                last_error = CompletionResult(
                    error="api_server_error",
                    details=_build_http_error_detail(endpoint.name, exc),
                )

                retryable = status_code is not None and 500 <= status_code < 600
                if retryable and attempt < self._max_retries:
                    await _sleep(attempt)
                    continue

                break

            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                logger.warning(
                    "Connection issue contacting KoboldCPP %s endpoint",
                    endpoint.name,
                    extra={"attempt": attempt, "error": str(exc)},
                )
                last_error = CompletionResult(
                    error="api_connection_error",
                    details=str(exc),
                )
                if attempt == self._max_retries:
                    break
                await _sleep(attempt)
                continue

            except httpx.HTTPError as exc:  # pragma: no cover - defensive safeguard
                logger.error(
                    "Unexpected request error contacting KoboldCPP %s endpoint",
                    endpoint.name,
                    extra={"error": str(exc)},
                )
                return CompletionResult(
                    error="api_request_error",
                    details=str(exc),
                )

            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                logger.error(
                    "Invalid JSON from KoboldCPP %s endpoint",
                    endpoint.name,
                    extra={"error": str(exc)},
                )
                return CompletionResult(
                    error="api_response_format_error",
                    details=f"Failed to decode JSON response from {endpoint.name} endpoint: {exc}",
                )

            completion_text = endpoint.extractor(payload)
            if completion_text is not None:
                logger.info(
                    "Received completion from KoboldCPP %s endpoint",
                    endpoint.name,
                    extra={"length": len(completion_text)},
                )
                return CompletionResult(completion=completion_text, raw_response=payload)

            last_error = CompletionResult(
                error="api_response_structure_error",
                details=f"Unexpected JSON payload from {endpoint.name} endpoint: {json.dumps(payload)[:200]}",
            )
            logger.error(
                "Unexpected payload structure from KoboldCPP %s endpoint",
                endpoint.name,
                extra={"payload": payload},
            )
            break

        return last_error or CompletionResult(
            error="api_unknown_error",
            details=f"All attempts to contact {endpoint.name} endpoint failed.",
        )


def _build_http_error_detail(endpoint_name: str, exc: httpx.HTTPStatusError) -> str:
    response = exc.response
    status = response.status_code if response is not None else "unknown"
    snippet = ""
    if response is not None and response.text:
        snippet = f" Response body: {response.text[:200]}"
    return f"HTTP error {status} from {endpoint_name} endpoint.{snippet}"


async def _sleep(attempt: int) -> None:
    backoff_index = min(attempt - 1, len(_BACKOFF_SECONDS) - 1)
    await anyio.sleep(_BACKOFF_SECONDS[backoff_index])


def _choose_error(errors: list[CompletionResult], *, default_detail: str) -> CompletionResult:
    for error in errors:
        if error.error not in _TRANSIENT_ERRORS:
            return error
    if errors:
        return errors[-1]
    return CompletionResult(error="api_unknown_error", details=default_detail)


def _build_default_pipeline(base_url: str) -> BackendPipeline:
    backend = KoboldBackend(base_url=base_url)
    slot = BackendSlotConfig(backend=backend)
    return BackendPipeline([slot])


def get_kobold_completion(
    prompt: str,
    kobold_url: str | None = None,
    max_length: int = 150,
    temperature: float = 0.7,
    top_p: float = 1.0,
) -> KoboldCompletionResult:
    base_url = (kobold_url or os.getenv("KOBOLDCPP_API_URL") or DEFAULT_KOBOLDCPP_API_URL).rstrip("/")
    request = CompletionRequest(
        prompt=prompt,
        max_tokens=max_length,
        temperature=temperature,
        top_p=top_p,
    )

    async def _runner() -> CompletionResult:
        pipeline = _build_default_pipeline(base_url)
        try:
            return await pipeline.acomplete(request)
        finally:
            await pipeline.aclose()

    return anyio.run(_runner)


async def async_get_kobold_completion(
    prompt: str,
    kobold_url: str | None = None,
    max_length: int = 150,
    temperature: float = 0.7,
    top_p: float = 1.0,
) -> KoboldCompletionResult:
    base_url = (kobold_url or os.getenv("KOBOLDCPP_API_URL") or DEFAULT_KOBOLDCPP_API_URL).rstrip("/")
    request = CompletionRequest(
        prompt=prompt,
        max_tokens=max_length,
        temperature=temperature,
        top_p=top_p,
    )
    pipeline = _build_default_pipeline(base_url)
    try:
        return await pipeline.acomplete(request)
    finally:
        await pipeline.aclose()


__all__ = [
    "KoboldCompletionResult",
    "KoboldBackend",
    "get_kobold_completion",
    "async_get_kobold_completion",
]

