from __future__ import annotations

import atexit
import json
import logging
import os
import signal
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from flask import Flask, Response, jsonify, request, g

from ai_ticket.metrics import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from werkzeug.middleware.proxy_fix import ProxyFix

from ai_ticket.events.inference import CompletionResponse, ErrorResponse, on_event


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

    logging.getLogger("werkzeug").setLevel(os.environ.get("WERKZEUG_LOG_LEVEL", log_level))


def _load_auth_tokens() -> set[str]:
    tokens: set[str] = set()
    token_env = os.environ.get("AI_TICKET_AUTH_TOKEN")
    if token_env:
        tokens.update(token.strip() for token in token_env.split(",") if token.strip())

    token_file = os.environ.get("AI_TICKET_AUTH_TOKEN_FILE")
    if token_file:
        path = Path(token_file)
        if path.exists():
            file_tokens = [line.strip() for line in path.read_text().splitlines() if line.strip()]
            tokens.update(file_tokens)
        else:
            logging.getLogger(__name__).warning(
                "Auth token file not found", extra={"token_file": token_file}
            )

    return tokens


class RateLimiter:
    """Simple in-memory sliding window rate limiter."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, float | None]:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] > self.window_seconds:
                events.popleft()

            if len(events) >= self.limit:
                retry_after = max(self.window_seconds - (now - events[0]), 0)
                return False, retry_after

            events.append(now)
            return True, None


def _configure_metrics() -> None:
    global REQUEST_COUNTER, REQUEST_ERRORS, REQUEST_LATENCY, IN_FLIGHT_GAUGE
    if REQUEST_COUNTER is not None:
        return

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


def _extract_bearer_token() -> str | None:
    auth_header = request.headers.get("Authorization")
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


configure_logging()
logger = logging.getLogger(__name__)

AUTH_TOKENS: set[str] = _load_auth_tokens()
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "120"))
RATE_LIMIT_WINDOW_SECONDS = float(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMITER = (
    RateLimiter(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS)
    if RATE_LIMIT_REQUESTS > 0 and RATE_LIMIT_WINDOW_SECONDS > 0
    else None
)
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

app = Flask(__name__)
trust_proxy_count = int(os.environ.get("TRUST_PROXY_COUNT", "0"))
if trust_proxy_count > 0:
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=trust_proxy_count,
        x_proto=trust_proxy_count,
        x_host=trust_proxy_count,
    )

EXEMPT_ENDPOINTS = {"health_check", "metrics"}


@app.before_request
def _start_request_timer() -> None:
    if IN_FLIGHT_GAUGE is not None:
        IN_FLIGHT_GAUGE.inc()
    g.request_start_time = time.perf_counter()


@app.before_request
def _enforce_security_controls():
    endpoint = request.endpoint or request.path
    if endpoint in EXEMPT_ENDPOINTS:
        return None

    if AUTH_TOKENS:
        provided_token = _extract_bearer_token() or request.headers.get("X-API-Key")
        if not provided_token:
            logger.warning("Missing authentication token", extra={"path": request.path})
            return jsonify(
                {"error": "unauthorised", "details": "Authentication token missing."}
            ), 401

        if provided_token not in AUTH_TOKENS:
            logger.warning("Invalid authentication token", extra={"path": request.path})
            return jsonify(
                {"error": "forbidden", "details": "Invalid authentication token."}
            ), 403

    if RATE_LIMITER:
        client_identifier = request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown"
        allowed, retry_after = RATE_LIMITER.allow(client_identifier)
        if not allowed:
            logger.warning(
                "Request rate limited",
                extra={"client": client_identifier, "retry_after": retry_after, "path": request.path},
            )
            response = jsonify({"error": "rate_limited", "details": "Too many requests."})
            if retry_after is not None:
                response.headers["Retry-After"] = f"{retry_after:.0f}"
            return response, 429

    return None


@app.after_request
def _record_metrics(response: Response) -> Response:
    endpoint = request.endpoint or request.path
    method = request.method
    status = response.status_code

    if REQUEST_COUNTER is not None:
        REQUEST_COUNTER.labels(method=method, endpoint=endpoint, status=status).inc()

    if REQUEST_ERRORS is not None and status >= 400:
        REQUEST_ERRORS.labels(method=method, endpoint=endpoint, status=status).inc()

    start_time = getattr(g, "request_start_time", None)
    if start_time is not None and REQUEST_LATENCY is not None:
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(
            time.perf_counter() - start_time
        )

    if IN_FLIGHT_GAUGE is not None:
        IN_FLIGHT_GAUGE.dec()

    response.headers.setdefault("X-Request-Processed-By", "ai-ticket")
    return response


@app.route("/event", methods=["POST"])
def handle_event():
    if not request.is_json:
        logger.error("Request is not JSON")
        return jsonify({"error": "invalid_request", "details": "Request must be JSON."}), 400

    event_data = request.get_json()
    logger.info(
        "Received event data",
        extra={"keys": list(event_data.keys()) if isinstance(event_data, Mapping) else None},
    )

    response = on_event(event_data)

    if isinstance(response, CompletionResponse):
        payload = asdict(response)
        logger.info("Successfully processed event", extra={"response_keys": list(payload.keys())})
        return jsonify(payload), 200

    if isinstance(response, ErrorResponse):
        payload = asdict(response)
        logger.error(
            "Error processing event",
            extra={"error_code": response.error, "status_code": response.status_code},
        )
        return jsonify(payload), response.status_code

    payload = _normalise_response(response)
    status_code = payload.pop("status_code", 200)
    if payload.get("error"):
        logger.error("Processing event returned legacy error", extra={"payload": payload})
    return jsonify(payload), status_code


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "shutdown_initiated": shutdown_event.is_set()}), 200


@app.route("/metrics", methods=["GET"])
def metrics() -> Response:
    return Response(generate_latest(), content_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
