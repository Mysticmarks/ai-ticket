"""Subset of the httpx API relying on requests for synchronous transport.

Like :mod:`ai_ticket._compat._anyio_stub`, this module is a pragmatic fallback
that keeps tests operational when the real :mod:`httpx` package is not
installable. Production deployments should still install the genuine library to
benefit from streaming, HTTP/2, and other advanced features.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import requests
from werkzeug.test import Client as WerkzeugClient
from werkzeug.wrappers import Response as WerkzeugResponse


class HTTPError(Exception):
    """Base class mirroring :class:`httpx.HTTPError`."""


class RequestError(HTTPError):
    def __init__(self, message: str, *, request: "Request" | None = None) -> None:
        super().__init__(message)
        self.request = request


class ConnectError(RequestError):
    """Connection-level failure."""


class ReadTimeout(RequestError):
    """Request timed out before completion."""


class HTTPStatusError(HTTPError):
    """Raised when a non-successful HTTP status is encountered."""

    def __init__(self, message: str, *, request: "Request", response: "Response") -> None:
        super().__init__(message)
        self.request = request
        self.response = response


@dataclass
class Limits:
    max_connections: int | None = None
    max_keepalive_connections: int | None = None


class Request:
    def __init__(self, method: str, url: str) -> None:
        self.method = method
        self.url = url


class Response:
    def __init__(
        self,
        status_code: int,
        *,
        content: bytes | None = None,
        json: Any | None = None,
        text: str | None = None,
        request: Request | None = None,
    ) -> None:
        self.status_code = status_code
        self.request = request
        if json is not None:
            self._content = json_dumps(json)
            self._json_data = json
        elif text is not None:
            self._content = text.encode()
            self._json_data = None
        else:
            self._content = content or b""
            self._json_data = None

    @property
    def content(self) -> bytes:
        return self._content

    @property
    def text(self) -> str:
        try:
            return self._content.decode()
        except Exception:  # pragma: no cover - defensive
            return ""

    def json(self) -> Any:
        if self._json_data is not None:
            return self._json_data
        return json.loads(self._content.decode())

    def raise_for_status(self) -> None:
        if 400 <= self.status_code < 600:
            request = self.request or Request("", "")
            raise HTTPStatusError("HTTP error", request=request, response=self)


def json_dumps(data: Any) -> bytes:
    return json.dumps(data).encode()


class WSGITransport:
    """WSGI transport that mirrors :class:`httpx.WSGITransport`."""

    def __init__(self, *, app: Any) -> None:
        self.app = app


class Client:
    """Synchronous WSGI client with the httpx API surface."""

    def __init__(self, *, transport: WSGITransport | None = None, base_url: str | None = None) -> None:
        if transport is None:
            raise ValueError("WSGITransport is required when using the lightweight httpx shim")
        self._transport = transport
        self._base_url = (base_url or "").rstrip("/")
        self._client = WerkzeugClient(transport.app, response_wrapper=WerkzeugResponse)

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # pragma: no cover - passthrough
        return False

    def post(
        self,
        url: str,
        *,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        path = url if url.startswith("/") else f"/{url}"
        werkzeug_response = self._client.post(path, json=json, headers=headers or {})
        try:
            payload = werkzeug_response.get_json()
        except Exception:  # pragma: no cover - depends on Flask internals
            payload = None

        request = Request("POST", f"{self._base_url}{path}")
        return Response(
            werkzeug_response.status_code,
            content=werkzeug_response.get_data(),
            json=payload,
            request=request,
        )

    def close(self) -> None:  # pragma: no cover - compatibility shim
        return None


class AsyncClient:
    """Async client delegating requests to :mod:`requests` in a worker thread."""

    def __init__(self, *, limits: Limits | None = None, timeout: float | None = None) -> None:
        self._session = requests.Session()
        self._timeout = timeout

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        timeout: float | None = None,
    ) -> Response:
        effective_timeout = timeout if timeout is not None else self._timeout

        def _do_post() -> requests.Response:
            return self._session.post(url, headers=headers, json=json, timeout=effective_timeout)

        try:
            response = await asyncio.to_thread(_do_post)
        except requests.exceptions.ConnectTimeout as exc:  # pragma: no cover - network env
            raise ReadTimeout(str(exc), request=Request("POST", url)) from exc
        except requests.exceptions.ConnectionError as exc:  # pragma: no cover - network env
            raise ConnectError(str(exc), request=Request("POST", url)) from exc
        except requests.exceptions.Timeout as exc:  # pragma: no cover - network env
            raise ReadTimeout(str(exc), request=Request("POST", url)) from exc
        except requests.exceptions.RequestException as exc:
            raise RequestError(str(exc), request=Request("POST", url)) from exc

        request = Request("POST", url)
        try:
            payload = response.json()
        except ValueError:
            payload = None
        response_content = Response(
            response.status_code,
            content=response.content,
            json=payload,
            request=request,
        )
        return response_content

    async def aclose(self) -> None:
        await asyncio.to_thread(self._session.close)


__all__ = [
    "Client",
    "AsyncClient",
    "Limits",
    "Request",
    "Response",
    "WSGITransport",
    "HTTPError",
    "HTTPStatusError",
    "RequestError",
    "ConnectError",
    "ReadTimeout",
]
