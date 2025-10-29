from __future__ import annotations

import atexit
import json
import logging
import os
import signal
import threading
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, AsyncGenerator, Mapping

import anyio

try:  # pragma: no cover - prefer real FastAPI when available
    from fastapi import FastAPI, HTTPException, Request, Response, status
    from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
    from starlette.middleware.proxy_headers import ProxyHeadersMiddleware
except ImportError:  # pragma: no cover - fallback for test environments without FastAPI
    from ai_ticket._compat.fastapi import (  # type: ignore
        FastAPI,
        HTTPException,
        Request,
        Response,
        status,
        FileResponse,
        JSONResponse,
        StreamingResponse,
        Middleware,
        BaseHTTPMiddleware,
        RequestResponseEndpoint,
        ProxyHeadersMiddleware,
    )

from ai_ticket.backends.base import StreamEvent, StreamingNotSupported
from ai_ticket.backends.kobold_client import async_stream_kobold_completion
from ai_ticket.events.common import validate_inference_event
from ai_ticket.events.inference import CompletionResponse, ErrorResponse, on_event
from ai_ticket.events.prompt_extraction import PromptExtractionResult, extract_prompt
from ai_ticket.events.validation import ValidationError
from ai_ticket.metrics import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from ai_ticket.observability import metrics_store
from ai_ticket.security import InMemoryRateLimiter, SQLiteRateLimiter, TokenManager
from ai_ticket.ui import get_ui_dist_path

try:  # pragma: no cover - optional dependency path
    from prometheus_client import REGISTRY  # type: ignore
except ImportError:  # pragma: no cover - exercised when prometheus is absent
    REGISTRY = None  # type: ignore[assignment]


class JsonFormatter(logging.Formatter):
    """Emit JSON-formatted log records with structured extras."""

    _STANDARD_ATTRS = {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
    }

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        record_message = record.getMessage()
        structured: dict[str, Any] = {
            "level": record.levelname,
            "message": record_message,
            "logger": record.name,
            "time": self.formatTime(record, self.datefmt),
        }

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in self._STANDARD_ATTRS and not key.startswith("_")
        }
        if extras:
            structured["extra"] = extras

        if record.exc_info:
            structured["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(structured, default=str)


def configure_logging() -> None:
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    logging.getLogger("uvicorn").setLevel(os.environ.get("UVICORN_LOG_LEVEL", log_level))


def _unregister_previous_metric_collectors(metric_names: list[str]) -> None:
    """Remove lingering collectors from the default Prometheus registry."""

    if REGISTRY is None:  # pragma: no cover - handled by compatibility layer
        return

    names_to_collectors = getattr(REGISTRY, "_names_to_collectors", {})
    collectors = {
        names_to_collectors.get(metric_name)
        for metric_name in metric_names
        if names_to_collectors.get(metric_name) is not None
    }

    for collector in collectors:
        try:
            REGISTRY.unregister(collector)  # type: ignore[arg-type]
        except KeyError:  # pragma: no cover - defensive guard
            continue


def _configure_metrics() -> None:
    global REQUEST_COUNTER, REQUEST_ERRORS, REQUEST_LATENCY, IN_FLIGHT_GAUGE
    if REQUEST_COUNTER is not None:
        return

    _unregister_previous_metric_collectors(
        [
            f"{METRICS_NAMESPACE}_http_requests",
            f"{METRICS_NAMESPACE}_http_requests_created",
            f"{METRICS_NAMESPACE}_http_requests_total",
            f"{METRICS_NAMESPACE}_http_request_errors",
            f"{METRICS_NAMESPACE}_http_request_errors_created",
            f"{METRICS_NAMESPACE}_http_request_errors_total",
            f"{METRICS_NAMESPACE}_http_request_duration_seconds",
            f"{METRICS_NAMESPACE}_http_request_duration_seconds_bucket",
            f"{METRICS_NAMESPACE}_http_request_duration_seconds_count",
            f"{METRICS_NAMESPACE}_http_request_duration_seconds_sum",
            f"{METRICS_NAMESPACE}_http_requests_in_flight",
        ]
    )

    REQUEST_COUNTER = Counter(
        "http_requests_total",
        "Total HTTP requests processed",
        ["method", "endpoint", "status"],
        namespace=METRICS_NAMESPACE,
    )
    REQUEST_ERRORS = Counter(
        "http_request_errors_total",
        "Total HTTP requests resulting in errors",
        ["method", "endpoint", "status"],
        namespace=METRICS_NAMESPACE,
    )
    REQUEST_LATENCY = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "endpoint"],
        namespace=METRICS_NAMESPACE,
    )
    IN_FLIGHT_GAUGE = Gauge(
        "http_requests_in_flight",
        "Current number of in-flight HTTP requests",
        namespace=METRICS_NAMESPACE,
    )


def _handle_shutdown_signal(signum: int, _frame: Any | None) -> None:
    logger.info("Received shutdown signal", extra={"signal": signum})
    shutdown_event.set()


def _handle_process_exit() -> None:
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        stream = getattr(handler, "stream", None)
        if stream is not None and getattr(stream, "closed", False):
            break
    else:
        logger.info("Process exiting; flushing logs and metrics")
    logging.shutdown()


def _extract_bearer_token(headers: Mapping[str, str]) -> str | None:
    auth_header: str | None = None
    for key, value in headers.items():
        if key.lower() == "authorization":
            auth_header = value
            break
    if not auth_header:
        return None
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def _normalise_response(response: Any) -> dict[str, Any]:
    if is_dataclass(response):
        return asdict(response)
    if isinstance(response, Mapping):
        return dict(response)
    return {"result": response}


def _serialize_stream_event(event: StreamEvent) -> dict[str, Any]:
    payload: dict[str, Any] = {"delta": event.delta, "done": event.done}
    if event.metadata is not None:
        payload["metadata"] = dict(event.metadata)
    return payload


def _streaming_error_response(error: ErrorResponse, *, start: float) -> StreamingResponse:
    duration = perf_counter() - start
    metrics_store.record_event(
        latency_s=duration,
        success=False,
        error_code=error.error,
        message=error.message,
    )

    payload: dict[str, Any] = {"error": error.error, "message": error.message, "done": True}
    if error.details is not None:
        payload["details"] = error.details

    async def _event_stream() -> AsyncGenerator[str, None]:
        yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(_event_stream(), media_type="text/event-stream", status_code=error.status_code)


def _build_streaming_success_response(
    prompt: str,
    *,
    start: float,
    kobold_url: str | None = None,
) -> StreamingResponse:
    logger.info("Starting streaming completion", extra={"prompt_preview": prompt[:80]})

    async def _event_stream() -> AsyncGenerator[str, None]:
        success = False
        error: tuple[str, str] | None = None
        try:
            async for chunk in async_stream_kobold_completion(
                prompt=prompt,
                kobold_url=kobold_url,
            ):
                payload = _serialize_stream_event(chunk)
                yield f"data: {json.dumps(payload)}\n\n"
            success = True
        except StreamingNotSupported as exc:
            logger.warning(
                "Streaming not supported by backend", extra={"error": str(exc)}
            )
            error = ("streaming_not_supported", str(exc))
            error_payload = {
                "error": "streaming_not_supported",
                "details": str(exc),
                "done": True,
            }
            yield f"data: {json.dumps(error_payload)}\n\n"
        except Exception as exc:  # pragma: no cover - defensive safeguard
            logger.exception("Streaming backend failure", extra={"error": str(exc)})
            error = ("streaming_error", str(exc))
            error_payload = {
                "error": "streaming_error",
                "details": str(exc),
                "done": True,
            }
            yield f"data: {json.dumps(error_payload)}\n\n"
        finally:
            duration = perf_counter() - start
            if success:
                metrics_store.record_event(latency_s=duration, success=True)
            else:
                error_code, message = error or (
                    "streaming_error",
                    "Streaming request failed.",
                )
                metrics_store.record_event(
                    latency_s=duration,
                    success=False,
                    error_code=error_code,
                    message=message,
                )

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


def _handle_streaming_event(event_data: Mapping[str, Any], *, start: float) -> Response:
    try:
        content_key = validate_inference_event(event_data)
        extraction: PromptExtractionResult = extract_prompt(event_data[content_key])
    except ValidationError as error:
        logger.warning(
            "Streaming inference validation failed",
            extra={
                "error_code": error.code,
                "status_code": error.status_code,
                "details": error.details,
            },
        )
        error_response = ErrorResponse(
            error=error.code,
            message=error.message,
            status_code=error.status_code,
            details=error.details,
        )
        return _streaming_error_response(error_response, start=start)

    kobold_url = event_data.get("kobold_url") if isinstance(event_data, Mapping) else None
    return _build_streaming_success_response(
        extraction.prompt,
        start=start,
        kobold_url=str(kobold_url) if kobold_url else None,
    )


configure_logging()
logger = logging.getLogger(__name__)

UI_DIST_PATH = get_ui_dist_path()
try:
    _token_reload_interval = float(os.environ.get("AI_TICKET_AUTH_TOKEN_RELOAD_INTERVAL", "30"))
except ValueError:
    _token_reload_interval = 30.0
TOKEN_MANAGER = TokenManager(reload_interval=max(_token_reload_interval, 1.0))
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "120"))
RATE_LIMIT_WINDOW_SECONDS = float(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_BACKEND = os.environ.get("RATE_LIMIT_BACKEND", "memory").lower()
RATE_LIMIT_CLEANUP = os.environ.get("RATE_LIMIT_CLEANUP_INTERVAL", "60")
try:
    rate_limit_cleanup_interval = max(float(RATE_LIMIT_CLEANUP), 1.0)
except ValueError:
    rate_limit_cleanup_interval = 60.0

if RATE_LIMIT_REQUESTS > 0 and RATE_LIMIT_WINDOW_SECONDS > 0:
    if RATE_LIMIT_BACKEND == "sqlite":
        rate_limit_path = os.environ.get("RATE_LIMIT_SQLITE_PATH", "rate_limit.sqlite3")
        RATE_LIMITER = SQLiteRateLimiter(
            rate_limit_path,
            limit=RATE_LIMIT_REQUESTS,
            window_seconds=RATE_LIMIT_WINDOW_SECONDS,
            cleanup_interval=rate_limit_cleanup_interval,
        )
    else:
        RATE_LIMITER = InMemoryRateLimiter(
            RATE_LIMIT_REQUESTS,
            RATE_LIMIT_WINDOW_SECONDS,
        )
else:
    RATE_LIMITER = None
METRICS_NAMESPACE = os.environ.get("METRICS_NAMESPACE", "ai_ticket")

REQUEST_COUNTER: Counter | None = None
REQUEST_ERRORS: Counter | None = None
REQUEST_LATENCY: Histogram | None = None
IN_FLIGHT_GAUGE: Gauge | None = None

_configure_metrics()

shutdown_event = threading.Event()
signal.signal(signal.SIGTERM, _handle_shutdown_signal)
signal.signal(signal.SIGINT, _handle_shutdown_signal)
atexit.register(_handle_process_exit)

EXEMPT_PATHS = {"/health", "/metrics"}


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if path in EXEMPT_PATHS:
            return await call_next(request)

        headers = {key: value for key, value in request.headers.items()}

        if TOKEN_MANAGER.has_tokens():
            provided_token = _extract_bearer_token(headers) or headers.get("X-API-Key")
            if not provided_token:
                logger.warning("Missing authentication token", extra={"path": path})
                return JSONResponse(
                    {"error": "unauthorised", "details": "Authentication token missing."},
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )

            if not TOKEN_MANAGER.is_valid(provided_token):
                logger.warning("Invalid authentication token", extra={"path": path})
                return JSONResponse(
                    {"error": "forbidden", "details": "Invalid authentication token."},
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        if RATE_LIMITER is not None:
            client_identifier = headers.get("X-Forwarded-For")
            if not client_identifier:
                client = request.client
                client_identifier = client.host if client else "unknown"
            allowed, retry_after = RATE_LIMITER.allow(client_identifier)
            if not allowed:
                logger.warning(
                    "Request rate limited",
                    extra={"client": client_identifier, "retry_after": retry_after, "path": path},
                )
                response = JSONResponse(
                    {"error": "rate_limited", "details": "Too many requests."},
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                )
                if retry_after is not None:
                    response.headers["Retry-After"] = f"{retry_after:.0f}"
                return response

        return await call_next(request)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        method = request.method

        if IN_FLIGHT_GAUGE is not None:
            IN_FLIGHT_GAUGE.inc()

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration = time.perf_counter() - start_time
            if REQUEST_COUNTER is not None:
                REQUEST_COUNTER.labels(method=method, endpoint=path, status=500).inc()
            if REQUEST_ERRORS is not None:
                REQUEST_ERRORS.labels(method=method, endpoint=path, status=500).inc()
            if REQUEST_LATENCY is not None:
                REQUEST_LATENCY.labels(method=method, endpoint=path).observe(duration)
            raise
        finally:
            if IN_FLIGHT_GAUGE is not None:
                IN_FLIGHT_GAUGE.dec()

        duration = time.perf_counter() - start_time

        status_code = response.status_code
        if REQUEST_COUNTER is not None:
            REQUEST_COUNTER.labels(method=method, endpoint=path, status=status_code).inc()
        if REQUEST_ERRORS is not None and status_code >= 400:
            REQUEST_ERRORS.labels(method=method, endpoint=path, status=status_code).inc()
        if REQUEST_LATENCY is not None:
            REQUEST_LATENCY.labels(method=method, endpoint=path).observe(duration)

        response.headers.setdefault("X-Request-Processed-By", "ai-ticket")
        return response


middleware_stack = [
    Middleware(SecurityMiddleware),
    Middleware(MetricsMiddleware),
]

trust_proxy_count = int(os.environ.get("TRUST_PROXY_COUNT", "0"))
if trust_proxy_count > 0:
    middleware_stack.append(Middleware(ProxyHeadersMiddleware, trusted_hosts=["*"]))

app = FastAPI(middleware=middleware_stack)


@app.on_event("shutdown")
async def _handle_shutdown() -> None:  # pragma: no cover - lifecycle
    shutdown_event.set()


@app.post("/event")
async def handle_event(request: Request) -> JSONResponse:
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" not in content_type:
        logger.error("Request is not JSON")
        metrics_store.record_event(
            latency_s=0.0,
            success=False,
            error_code="invalid_request",
            message="Request must be JSON.",
        )
        return JSONResponse(
            {"error": "invalid_request", "details": "Request must be JSON."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        event_data = await request.json()
    except json.JSONDecodeError:
        logger.error("Malformed JSON payload")
        metrics_store.record_event(
            latency_s=0.0,
            success=False,
            error_code="invalid_request",
            message="Request must be JSON.",
        )
        return JSONResponse(
            {"error": "invalid_request", "details": "Request must be JSON."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    logger.info(
        "Received event data",
        extra={"keys": list(event_data.keys()) if isinstance(event_data, Mapping) else None},
    )

    start = perf_counter()

    if bool(getattr(event_data, "get", lambda *_: False)("stream")):
        return _handle_streaming_event(event_data, start=start)

    try:
        response = await anyio.to_thread.run_sync(on_event, event_data)
    except Exception as error:  # pragma: no cover - defensive guard
        duration = perf_counter() - start
        logger.exception("Unhandled exception processing event")
        metrics_store.record_event(
            latency_s=duration,
            success=False,
            error_code="unhandled_exception",
            message=str(error),
        )
        return JSONResponse(
            {"error": "internal_error", "details": "An unexpected error occurred."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    duration = perf_counter() - start

    if isinstance(response, CompletionResponse):
        payload = asdict(response)
        logger.info("Successfully processed event", extra={"response_keys": list(payload.keys())})
        metrics_store.record_event(latency_s=duration, success=True)
        return JSONResponse(payload, status_code=status.HTTP_200_OK)

    if isinstance(response, ErrorResponse):
        payload = asdict(response)
        logger.error(
            "Error processing event",
            extra={"error_code": response.error, "status_code": response.status_code},
        )
        metrics_store.record_event(
            latency_s=duration,
            success=False,
            error_code=response.error,
            message=response.message,
        )
        return JSONResponse(payload, status_code=response.status_code)

    payload = _normalise_response(response)
    status_code = payload.pop("status_code", status.HTTP_200_OK)
    if payload.get("error"):
        logger.error("Processing event returned legacy error", extra={"payload": payload})
        metrics_store.record_event(
            latency_s=duration,
            success=False,
            error_code=str(payload.get("error")),
            message=str(payload.get("details")) if payload.get("details") else None,
        )
    else:
        metrics_store.record_event(latency_s=duration, success=True)
    return JSONResponse(payload, status_code=status_code)


@app.get("/health")
async def health_check() -> JSONResponse:
    return JSONResponse({"status": "healthy", "shutdown_initiated": shutdown_event.is_set()})


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/metrics/summary")
async def metrics_summary() -> JSONResponse:
    return JSONResponse(metrics_store.snapshot())


async def _metrics_event_stream() -> AsyncGenerator[str, None]:
    queue = metrics_store.subscribe()
    try:
        yield f"data: {metrics_store.snapshot_json()}\n\n"
        while True:
            payload = await anyio.to_thread.run_sync(queue.get)
            yield f"data: {json.dumps(payload)}\n\n"
    finally:
        metrics_store.unsubscribe(queue)


@app.get("/api/metrics/stream")
async def metrics_stream() -> StreamingResponse:
    return StreamingResponse(_metrics_event_stream(), media_type="text/event-stream")


def _resolve_dashboard_asset(asset_path: str | None) -> Path:
    if not UI_DIST_PATH.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard assets are not available. Build the UI bundle first.",
        )

    if asset_path:
        resolved_path = UI_DIST_PATH / asset_path
        if resolved_path.exists() and resolved_path.is_file():
            return resolved_path

    index_path = UI_DIST_PATH / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard index not found.")
    return index_path


@app.get("/dashboard")
@app.get("/dashboard/{asset_path:path}")
async def dashboard(asset_path: str | None = None) -> FileResponse:
    resolved_path = _resolve_dashboard_asset(asset_path)
    return FileResponse(resolved_path)


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    port = int(os.environ.get("PORT", "5000"))
    uvicorn.run("ai_ticket.server:app", host="0.0.0.0", port=port, reload=False)
