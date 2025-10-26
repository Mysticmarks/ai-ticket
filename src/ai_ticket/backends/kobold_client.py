"""KoboldCPP backend client."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Callable, Final

import requests
from requests import Response


logger = logging.getLogger(__name__)


DEFAULT_KOBOLDCPP_API_URL: Final[str] = "http://localhost:5001/api"
MAX_RETRIES: Final[int] = 3
_BACKOFF_SECONDS: Final[tuple[float, ...]] = (0.1, 0.25, 0.5)


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

    base_url = (kobold_url or os.getenv("KOBOLDCPP_API_URL") or DEFAULT_KOBOLDCPP_API_URL).rstrip("/")

    if not base_url:
        logger.error("KoboldCPP base URL is missing.")
        return KoboldCompletionResult(
            error="configuration_error",
            details="KOBOLDCPP_API_URL is not configured.",
        )

    headers = {"Content-Type": "application/json"}
    last_error: KoboldCompletionResult | None = None

    for endpoint in _ENDPOINTS:
        endpoint_url = f"{base_url}{endpoint.path}"
        logger.info("Attempting KoboldCPP %s endpoint", endpoint.name, extra={"url": endpoint_url})

        for attempt in range(1, MAX_RETRIES + 1):
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
                    "HTTP error from KoboldCPP %s endpoint", endpoint.name,
                    extra={"status_code": status_code, "attempt": attempt},
                )

                if status_code in {401, 403}:
                    return KoboldCompletionResult(
                        error="api_authentication_error",
                        details=f"Authentication failed for {endpoint.name} endpoint.",
                    )

                if status_code == 429:
                    last_error = KoboldCompletionResult(
                        error="api_rate_limited",
                        details=f"Rate limit encountered for {endpoint.name} endpoint.",
                    )
                    _sleep(attempt)
                    continue

                if status_code is not None and 400 <= status_code < 500:
                    return KoboldCompletionResult(
                        error="api_client_error",
                        details=_build_http_error_detail(endpoint.name, exc),
                    )

                last_error = KoboldCompletionResult(
                    error="api_server_error",
                    details=_build_http_error_detail(endpoint.name, exc),
                )

                retryable = status_code is not None and 500 <= status_code < 600
                if retryable and attempt < MAX_RETRIES:
                    _sleep(attempt)
                    continue

                break

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:  # type: ignore[attr-defined]
                logger.warning(
                    "Connection issue contacting KoboldCPP %s endpoint", endpoint.name,
                    extra={"attempt": attempt, "error": str(exc)},
                )
                last_error = KoboldCompletionResult(
                    error="api_connection_error",
                    details=str(exc),
                )
                if attempt == MAX_RETRIES:
                    break
                _sleep(attempt)
                continue

            except requests.exceptions.RequestException as exc:  # type: ignore[attr-defined]
                logger.error(
                    "Unexpected request error contacting KoboldCPP %s endpoint", endpoint.name,
                    extra={"error": str(exc)},
                )
                last_error = KoboldCompletionResult(
                    error="api_request_error",
                    details=str(exc),
                )
                break

            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                logger.error(
                    "Invalid JSON from KoboldCPP %s endpoint", endpoint.name,
                    extra={"error": str(exc)},
                )
                return KoboldCompletionResult(
                    error="api_response_format_error",
                    details=f"Failed to decode JSON response from {endpoint.name} endpoint: {exc}",
                )

            completion_text = endpoint.extractor(payload)
            if completion_text is not None:
                logger.info(
                    "Received completion from KoboldCPP %s endpoint", endpoint.name,
                    extra={"length": len(completion_text)},
                )
                return KoboldCompletionResult(completion=completion_text)

            last_error = KoboldCompletionResult(
                error="api_response_structure_error",
                details=f"Unexpected JSON payload from {endpoint.name} endpoint: {json.dumps(payload)[:200]}",
            )
            logger.error(
                "Unexpected payload structure from KoboldCPP %s endpoint", endpoint.name,
                extra={"payload": payload},
            )
            break

        if last_error and last_error.error not in {
            "api_connection_error",
            "api_server_error",
            "api_rate_limited",
            "api_request_error",
        }:
            return last_error

    return last_error or KoboldCompletionResult(
        error="api_unknown_error",
        details="All attempts to contact KoboldCPP API failed.",
    )


def _sleep(attempt: int) -> None:
    backoff_index = min(attempt - 1, len(_BACKOFF_SECONDS) - 1)
    time.sleep(_BACKOFF_SECONDS[backoff_index])


def _build_http_error_detail(endpoint_name: str, exc: requests.exceptions.HTTPError) -> str:
    response: Response | None = exc.response
    status = response.status_code if response is not None else "unknown"
    snippet = ""
    if response is not None and response.text:
        snippet = f" Response body: {response.text[:200]}"
    return f"HTTP error {status} from {endpoint_name} endpoint.{snippet}"


__all__ = ["KoboldCompletionResult", "get_kobold_completion"]
