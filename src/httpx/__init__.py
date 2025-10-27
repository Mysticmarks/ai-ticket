"""Minimal httpx-compatible client built on top of requests."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import requests


class HTTPError(Exception):
    pass


class RequestError(HTTPError):
    def __init__(self, message: str, *, request: "Request" | None = None) -> None:
        super().__init__(message)
        self.request = request


class ConnectError(RequestError):
    pass


class ReadTimeout(RequestError):
    pass


class HTTPStatusError(HTTPError):
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
            self._content = json_encode(json)
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


def json_encode(data: Any) -> bytes:
    return json.dumps(data).encode()


class AsyncClient:
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
    "AsyncClient",
    "Limits",
    "Request",
    "Response",
    "HTTPError",
    "HTTPStatusError",
    "RequestError",
    "ConnectError",
    "ReadTimeout",
]

