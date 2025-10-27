"""KoboldCPP backend client."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Callable, Final

import requests
from requests import Response

from ai_ticket.telemetry import SpanKind, Status, StatusCode, get_meter, get_tracer


logger = logging.getLogger(__name__)

_TRACER = get_tracer(__name__)
_METER = get_meter(__name__)

_REQUEST_COUNTER = _METER.create_counter(
    "ai_ticket_kobold_requests_total",
    description="Total number of HTTP attempts performed against the KoboldCPP backend.",
)
_REQUEST_FAILURES = _METER.create_counter(
    "ai_ticket_kobold_request_failures_total",
    description="Number of KoboldCPP requests that ended in a non-success status.",
)
_REQUEST_RETRIES = _METER.create_counter(
    "ai_ticket_kobold_request_retries_total",
    description="Count of retry attempts performed when contacting KoboldCPP endpoints.",
)
_REQUEST_LATENCY = _METER.create_histogram(
    "ai_ticket_kobold_request_duration_seconds",
    unit="s",
    description="Latency of HTTP calls issued to KoboldCPP endpoints.",
)


DEFAULT_KOBOLDCPP_API_URL: Final[str] = "http://localhost:5001/api"
MAX_RETRIES: Final[int] = 3
_BACKOFF_SECONDS: Final[tuple[float, ...]] = (0.1, 0.25, 0.5)
_TRANSIENT_ERRORS: Final[frozenset[str]] = frozenset(
    {
        "api_connection_error",
        "api_server_error",
        "api_rate_limited",
        "api_request_error",
    }
)


@dataclass(frozen=True)
class KoboldCompletionResult:
    """Standard response wrapper for backend completions."""

    completion: str | None = None
    error: str | None = None
    details: str | None = None

    @property
    def is_success(self) -> bool:
        return self.completion is not None


@dataclass(frozen=True)
class _EndpointSpec:
    name: str
    path: str
    payload_builder: Callable[[str, int, float, float], dict]
    extractor: Callable[[dict], str | None]


def _chat_payload(prompt: str, max_length: int, temperature: float, top_p: float) -> dict:
    return {
        "model": "koboldcpp-model",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_length,
        "temperature": temperature,
        "top_p": top_p,
    }


def _chat_extractor(data: dict) -> str | None:
    try:
        message = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(message, str):
        return None
    return message.strip()


def _completion_payload(prompt: str, max_length: int, temperature: float, top_p: float) -> dict:
    return {
        "model": "koboldcpp-model",
        "prompt": prompt,
        "max_tokens": max_length,
        "temperature": temperature,
        "top_p": top_p,
    }


def _completion_extractor(data: dict) -> str | None:
    try:
        text = data["choices"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(text, str):
        return None
    return text.strip()


_ENDPOINTS: Final[tuple[_EndpointSpec, ...]] = (
    _EndpointSpec(
        name="chat",
        path="/v1/chat/completions",
        payload_builder=_chat_payload,
        extractor=_chat_extractor,
    ),
    _EndpointSpec(
        name="completion",
        path="/v1/completions",
        payload_builder=_completion_payload,
        extractor=_completion_extractor,
    ),
)


def get_kobold_completion(
    prompt: str,
    kobold_url: str | None = None,
    max_length: int = 150,
    temperature: float = 0.7,
    top_p: float = 1.0,
) -> KoboldCompletionResult:
    """Fetch a text completion from a KoboldCPP API with retries."""

    with _TRACER.start_as_current_span("kobold.get_completion") as span:
        span.set_attribute("kobold.mode", "sync")
        span.set_attribute("kobold.max_length", max_length)
        span.set_attribute("kobold.temperature", temperature)
        span.set_attribute("kobold.top_p", top_p)

        base_url = (kobold_url or os.getenv("KOBOLDCPP_API_URL") or DEFAULT_KOBOLDCPP_API_URL).rstrip("/")
        span.set_attribute("kobold.base_url", base_url or "")

        if not base_url:
            logger.error("KoboldCPP base URL is missing.")
            span.set_status(Status(StatusCode.ERROR, "configuration_error"))
            return KoboldCompletionResult(
                error="configuration_error",
                details="KOBOLDCPP_API_URL is not configured.",
            )

        headers = {"Content-Type": "application/json"}
        errors: list[KoboldCompletionResult] = []

        for endpoint in _ENDPOINTS:
            result = _fetch_from_endpoint(
                endpoint=endpoint,
                endpoint_url=f"{base_url}{endpoint.path}",
                prompt=prompt,
                max_length=max_length,
                temperature=temperature,
                top_p=top_p,
                headers=headers,
            )
            if result.is_success:
                span.set_status(Status(StatusCode.OK))
                return result
            errors.append(result)
            if result.error not in _TRANSIENT_ERRORS:
                span.set_status(Status(StatusCode.ERROR, result.error or "error"))
                return result

        final_error = _choose_error(
            errors,
            default_detail="All attempts to contact KoboldCPP API failed.",
        )
        span.set_status(Status(StatusCode.ERROR, final_error.error or "error"))
        return final_error


async def async_get_kobold_completion(
    prompt: str,
    kobold_url: str | None = None,
    max_length: int = 150,
    temperature: float = 0.7,
    top_p: float = 1.0,
) -> KoboldCompletionResult:
    """Asynchronously fetch a text completion from a KoboldCPP API."""

    with _TRACER.start_as_current_span("kobold.async_get_completion") as span:
        span.set_attribute("kobold.mode", "async")
        span.set_attribute("kobold.max_length", max_length)
        span.set_attribute("kobold.temperature", temperature)
        span.set_attribute("kobold.top_p", top_p)

        base_url = (kobold_url or os.getenv("KOBOLDCPP_API_URL") or DEFAULT_KOBOLDCPP_API_URL).rstrip("/")
        span.set_attribute("kobold.base_url", base_url or "")

        if not base_url:
            logger.error("KoboldCPP base URL is missing.")
            span.set_status(Status(StatusCode.ERROR, "configuration_error"))
            return KoboldCompletionResult(
                error="configuration_error",
                details="KOBOLDCPP_API_URL is not configured.",
            )

        headers = {"Content-Type": "application/json"}

        async def _execute(endpoint: _EndpointSpec) -> KoboldCompletionResult:
            return await asyncio.to_thread(
                _fetch_from_endpoint,
                endpoint,
                f"{base_url}{endpoint.path}",
                prompt,
                max_length,
                temperature,
                top_p,
                headers,
            )

        tasks = [asyncio.create_task(_execute(endpoint)) for endpoint in _ENDPOINTS]
        errors: list[KoboldCompletionResult] = []

        try:
            for task in asyncio.as_completed(tasks):
                result = await task
                if result.is_success:
                    span.set_status(Status(StatusCode.OK))
                    for pending in tasks:
                        if pending is not task and not pending.done():
                            pending.cancel()
                    return result
                errors.append(result)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        final_error = _choose_error(
            errors,
            default_detail="All asynchronous attempts to contact KoboldCPP API failed.",
        )
        span.set_status(Status(StatusCode.ERROR, final_error.error or "error"))
        return final_error


def _fetch_from_endpoint(
    endpoint: _EndpointSpec,
    endpoint_url: str,
    prompt: str,
    max_length: int,
    temperature: float,
    top_p: float,
    headers: dict[str, str],
) -> KoboldCompletionResult:
    last_error: KoboldCompletionResult | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        attempt_attributes = {"endpoint": endpoint.name, "attempt": attempt}
        _REQUEST_COUNTER.add(1, attempt_attributes)
        if attempt > 1:
            _REQUEST_RETRIES.add(1, attempt_attributes)

        logger.info(
            "Attempting KoboldCPP %s endpoint",
            endpoint.name,
            extra={"url": endpoint_url, "attempt": attempt},
        )

        status_label = "ok"
        start_time = time.perf_counter()

        try:
            with _TRACER.start_as_current_span(
                "kobold.request",
                kind=SpanKind.CLIENT,
            ) as span:
                span.set_attribute("http.method", "POST")
                span.set_attribute("http.url", endpoint_url)
                span.set_attribute("kobold.endpoint", endpoint.name)
                span.set_attribute("kobold.attempt", attempt)
                try:
                    response = requests.post(
                        endpoint_url,
                        headers=headers,
                        json=endpoint.payload_builder(prompt, max_length, temperature, top_p),
                        timeout=120,
                    )
                    response.raise_for_status()
                except requests.exceptions.HTTPError as exc:  # type: ignore[attr-defined]
                    status_code = exc.response.status_code if exc.response is not None else None
                    logger.warning(
                        "HTTP error from KoboldCPP %s endpoint",
                        endpoint.name,
                        extra={"status_code": status_code, "attempt": attempt},
                    )
                    span.record_exception(exc)
                    if status_code in {401, 403}:
                        span.set_status(Status(StatusCode.ERROR, "api_authentication_error"))
                        _REQUEST_FAILURES.add(1, {**attempt_attributes, "error": "api_authentication_error"})
                        status_label = "error"
                        return KoboldCompletionResult(
                            error="api_authentication_error",
                            details=_build_http_error_detail(endpoint.name, exc),
                        )

                    if status_code == 429:
                        span.set_status(Status(StatusCode.ERROR, "api_rate_limited"))
                        last_error = KoboldCompletionResult(
                            error="api_rate_limited",
                            details=_build_http_error_detail(endpoint.name, exc),
                        )
                        _REQUEST_FAILURES.add(1, {**attempt_attributes, "error": "api_rate_limited"})
                        status_label = "error"
                        _sleep(attempt)
                        continue

                    if status_code is not None and 400 <= status_code < 500:
                        span.set_status(Status(StatusCode.ERROR, "api_client_error"))
                        _REQUEST_FAILURES.add(1, {**attempt_attributes, "error": "api_client_error"})
                        status_label = "error"
                        return KoboldCompletionResult(
                            error="api_client_error",
                            details=_build_http_error_detail(endpoint.name, exc),
                        )

                    last_error = KoboldCompletionResult(
                        error="api_server_error",
                        details=_build_http_error_detail(endpoint.name, exc),
                    )
                    span.set_status(Status(StatusCode.ERROR, "api_server_error"))
                    _REQUEST_FAILURES.add(1, {**attempt_attributes, "error": "api_server_error"})

                    retryable = status_code is not None and 500 <= status_code < 600
                    status_label = "error"
                    if retryable and attempt < MAX_RETRIES:
                        _sleep(attempt)
                        continue

                    break

                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:  # type: ignore[attr-defined]
                    logger.warning(
                        "Connection issue contacting KoboldCPP %s endpoint",
                        endpoint.name,
                        extra={"attempt": attempt, "error": str(exc)},
                    )
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, "api_connection_error"))
                    last_error = KoboldCompletionResult(
                        error="api_connection_error",
                        details=str(exc),
                    )
                    _REQUEST_FAILURES.add(1, {**attempt_attributes, "error": "api_connection_error"})
                    status_label = "error"
                    if attempt == MAX_RETRIES:
                        break
                    _sleep(attempt)
                    continue

                except requests.exceptions.RequestException as exc:  # type: ignore[attr-defined]
                    logger.error(
                        "Unexpected request error contacting KoboldCPP %s endpoint",
                        endpoint.name,
                        extra={"error": str(exc)},
                    )
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, "api_request_error"))
                    _REQUEST_FAILURES.add(1, {**attempt_attributes, "error": "api_request_error"})
                    status_label = "error"
                    return KoboldCompletionResult(
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
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, "api_response_format_error"))
                    _REQUEST_FAILURES.add(1, {**attempt_attributes, "error": "api_response_format_error"})
                    status_label = "error"
                    return KoboldCompletionResult(
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
                    span.set_status(Status(StatusCode.OK))
                    return KoboldCompletionResult(completion=completion_text)

                last_error = KoboldCompletionResult(
                    error="api_response_structure_error",
                    details=f"Unexpected JSON payload from {endpoint.name} endpoint: {json.dumps(payload)[:200]}",
                )
                span.set_status(Status(StatusCode.ERROR, "api_response_structure_error"))
                _REQUEST_FAILURES.add(1, {**attempt_attributes, "error": "api_response_structure_error"})
                logger.error(
                    "Unexpected payload structure from KoboldCPP %s endpoint",
                    endpoint.name,
                    extra={"payload": payload},
                )
                status_label = "error"
                break
        finally:
            duration = time.perf_counter() - start_time
            _REQUEST_LATENCY.record(duration, {**attempt_attributes, "status": status_label})

    return last_error or KoboldCompletionResult(
        error="api_unknown_error",
        details=f"All attempts to contact {endpoint.name} endpoint failed.",
    )


def _sleep(attempt: int) -> None:
    backoff_index = min(attempt - 1, len(_BACKOFF_SECONDS) - 1)
    time.sleep(_BACKOFF_SECONDS[backoff_index])


def _choose_error(errors: list[KoboldCompletionResult], *, default_detail: str) -> KoboldCompletionResult:
    for error in errors:
        if error.error not in _TRANSIENT_ERRORS:
            return error
    if errors:
        return errors[-1]
    return KoboldCompletionResult(error="api_unknown_error", details=default_detail)


def _build_http_error_detail(endpoint_name: str, exc: requests.exceptions.HTTPError) -> str:
    response: Response | None = exc.response
    status = response.status_code if response is not None else "unknown"
    snippet = ""
    if response is not None and response.text:
        snippet = f" Response body: {response.text[:200]}"
    return f"HTTP error {status} from {endpoint_name} endpoint.{snippet}"


__all__ = [
    "KoboldCompletionResult",
    "get_kobold_completion",
    "async_get_kobold_completion",
]
