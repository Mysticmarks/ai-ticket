from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Iterable, Iterator


class _StatusCodes:
    HTTP_200_OK = 200
    HTTP_400_BAD_REQUEST = 400
    HTTP_401_UNAUTHORIZED = 401
    HTTP_403_FORBIDDEN = 403
    HTTP_404_NOT_FOUND = 404
    HTTP_429_TOO_MANY_REQUESTS = 429
    HTTP_500_INTERNAL_SERVER_ERROR = 500
    HTTP_502_BAD_GATEWAY = 502


status = _StatusCodes()


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str | None = None) -> None:
        super().__init__(detail or "HTTPException")
        self.status_code = status_code
        self.detail = detail or ""


class URL:
    def __init__(self, path: str) -> None:
        self.path = path


class Headers:
    def __init__(self, raw: Iterable[tuple[bytes, bytes]]) -> None:
        self._data = {key.decode().lower(): value.decode() for key, value in raw}

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._data.get(key.lower(), default)

    def items(self) -> list[tuple[str, str]]:
        return list(self._data.items())

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)


class Client:
    def __init__(self, host: str | None, port: int | None) -> None:
        self.host = host or ""
        self.port = port


class Request:
    def __init__(self, scope: dict[str, Any], receive: Callable[[], Awaitable[dict[str, Any]]]) -> None:
        self.scope = scope
        self._receive = receive
        self._body: bytes | None = None
        self.headers = Headers(scope.get("headers", []))
        client = scope.get("client")
        if client is None:
            self.client: Client | None = None
        else:
            self.client = Client(client[0], client[1])
        self.method = scope.get("method", "GET").upper()
        self.url = URL(scope.get("path", "/"))

    async def body(self) -> bytes:
        if self._body is None:
            chunks: list[bytes] = []
            more_body = True
            while more_body:
                message = await self._receive()
                chunks.append(message.get("body", b""))
                more_body = message.get("more_body", False)
            self._body = b"".join(chunks)
        return self._body

    async def json(self) -> Any:
        data = await self.body()
        if not data:
            raise json.JSONDecodeError("Empty body", "", 0)
        return json.loads(data.decode())


class Response:
    def __init__(
        self,
        content: bytes | str = b"",
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str | None = None,
    ) -> None:
        if isinstance(content, str):
            content = content.encode()
        self.body = content
        self.status_code = status_code
        self.headers: dict[str, str] = {key.lower(): value for key, value in (headers or {}).items()}
        if media_type is not None:
            self.headers.setdefault("content-type", media_type)

    def setdefault(self, key: str, value: str) -> None:
        self.headers.setdefault(key.lower(), value)

    async def __call__(self, scope: dict[str, Any], receive: Callable[[], Awaitable[dict[str, Any]]], send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        await self.send(send)

    async def send(self, send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        headers = [(key.encode(), value.encode()) for key, value in self.headers.items()]
        await send({"type": "http.response.start", "status": self.status_code, "headers": headers})
        await send({"type": "http.response.body", "body": self.body, "more_body": False})


class JSONResponse(Response):
    def __init__(self, content: Any, *, status_code: int = 200, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(content).encode()
        combined_headers = {"content-type": "application/json"}
        if headers:
            combined_headers.update({key.lower(): value for key, value in headers.items()})
        super().__init__(body, status_code=status_code, headers=combined_headers)


class StreamingResponse(Response):
    def __init__(
        self,
        content: Iterable[bytes] | AsyncIterator[bytes],
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str | None = None,
    ) -> None:
        super().__init__(b"", status_code=status_code, headers=headers, media_type=media_type)
        self._content = content

    async def send(self, send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        headers = [(key.encode(), value.encode()) for key, value in self.headers.items()]
        await send({"type": "http.response.start", "status": self.status_code, "headers": headers})

        if hasattr(self._content, "__aiter__"):
            async for chunk in self._content:  # type: ignore[attr-defined]
                if isinstance(chunk, str):
                    chunk = chunk.encode()
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
        else:
            for chunk in self._content:  # type: ignore[assignment]
                if isinstance(chunk, str):
                    chunk = chunk.encode()
                await send({"type": "http.response.body", "body": chunk, "more_body": True})

        await send({"type": "http.response.body", "body": b"", "more_body": False})


class FileResponse(Response):
    def __init__(self, path: Path | str, *, media_type: str | None = None) -> None:
        path = Path(path)
        content = path.read_bytes()
        guessed = media_type or _guess_media_type(path)
        super().__init__(content, status_code=200, media_type=guessed)


def _guess_media_type(path: Path) -> str:
    if path.suffix == ".json":
        return "application/json"
    if path.suffix in {".html", ".htm"}:
        return "text/html; charset=utf-8"
    if path.suffix == ".css":
        return "text/css"
    if path.suffix == ".js":
        return "application/javascript"
    return "application/octet-stream"


RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]


@dataclass
class Middleware:
    cls: type
    options: dict[str, Any] | None = None


class BaseHTTPMiddleware:
    def __init__(self, app: RequestResponseEndpoint, **options: Any) -> None:
        self.app = app
        self.options = options

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:  # pragma: no cover - override required
        return await call_next(request)

    async def __call__(self, request: Request) -> Response:
        return await self.dispatch(request, self.app)


class ProxyHeadersMiddleware:
    def __init__(self, app: RequestResponseEndpoint, **_: Any) -> None:
        self.app = app

    async def __call__(self, request: Request) -> Response:
        return await self.app(request)


@dataclass
class _Route:
    path: str
    endpoint: Callable[..., Awaitable[Response] | Response]
    methods: set[str]
    param_name: str | None = None
    prefix: str | None = None


class FastAPI:
    def __init__(self, *, middleware: list[Middleware] | None = None) -> None:
        self._routes: list[_Route] = []
        self._middleware = middleware or []
        self._shutdown_handlers: list[Callable[[], Any]] = []

    def post(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._register(path, {"POST"})

    def get(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._register(path, {"GET"})

    def _register(self, path: str, methods: set[str]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            if path.endswith("{asset_path:path}"):
                base = path.split("{", 1)[0].rstrip("/")
                param_name = path.split("{", 1)[1].split(":", 1)[0]
                self._routes.append(
                    _Route(base, func, methods, param_name=param_name, prefix=f"{base}/")
                )
            else:
                self._routes.append(_Route(path.rstrip("/"), func, methods))
            return func

        return decorator

    def on_event(self, event: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            if event == "shutdown":
                self._shutdown_handlers.append(func)
            return func

        return decorator

    async def __call__(self, scope: dict[str, Any], receive: Callable[[], Awaitable[dict[str, Any]]], send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        scope_type = scope.get("type")
        if scope_type == "lifespan":
            await self._handle_lifespan(receive, send)
            return
        if scope_type != "http":  # pragma: no cover - unsupported scope
            return

        request = Request(scope, receive)
        route, params = self._match_route(request.url.path, request.method)
        if route is None:
            response: Response = JSONResponse({"detail": "Not Found"}, status_code=status.HTTP_404_NOT_FOUND)
        else:
            handler = self._build_handler(route, params)
            try:
                response = await handler(request)
            except HTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

        await response(scope, receive, send)

    async def _handle_lifespan(
        self,
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        while True:  # pragma: no cover - minimal lifespan handling
            message = await receive()
            message_type = message.get("type")
            if message_type == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message_type == "lifespan.shutdown":
                for handler in self._shutdown_handlers:
                    result = handler()
                    if asyncio.iscoroutine(result):
                        await result
                await send({"type": "lifespan.shutdown.complete"})
                return

    def _build_handler(self, route: _Route, params: dict[str, str]) -> Callable[[Request], Awaitable[Response]]:
        async def endpoint_handler(request: Request) -> Response:
            func = route.endpoint
            call_kwargs: dict[str, Any] = {}
            if "request" in inspect.signature(func).parameters:
                call_kwargs["request"] = request
            call_kwargs.update(params)

            result = func(**call_kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            if isinstance(result, Response):
                return result
            if isinstance(result, dict):
                return JSONResponse(result)
            return Response(str(result))

        handler: Callable[[Request], Awaitable[Response]] = endpoint_handler
        for middleware in reversed(self._middleware):
            options = middleware.options or {}
            handler = middleware.cls(handler, **options)  # type: ignore[call-arg]
        return handler

    def _match_route(self, path: str, method: str) -> tuple[_Route | None, dict[str, str]]:
        normalised_path = path.rstrip("/") or "/"
        for route in self._routes:
            if method not in route.methods:
                continue
            if route.param_name:
                prefix = route.prefix or ""
                if not path.startswith(prefix):
                    continue
                param_value = path[len(prefix):]
                return route, {route.param_name: param_value}
            if route.path == normalised_path:
                return route, {}
        return None, {}


__all__ = [
    "FastAPI",
    "HTTPException",
    "Request",
    "Response",
    "JSONResponse",
    "StreamingResponse",
    "FileResponse",
    "Middleware",
    "BaseHTTPMiddleware",
    "ProxyHeadersMiddleware",
    "RequestResponseEndpoint",
    "status",
]
