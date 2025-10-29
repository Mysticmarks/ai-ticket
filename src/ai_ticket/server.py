from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, is_dataclass
from time import perf_counter
from typing import Any, Mapping

from flask import Flask, Response, abort, jsonify, request, send_from_directory, g
from flask import stream_with_context
import atexit
import signal
import threading
import time

from ai_ticket.metrics import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

try:  # pragma: no cover - optional dependency path
    from prometheus_client import REGISTRY  # type: ignore
except ImportError:  # pragma: no cover - exercised when prometheus is absent
    REGISTRY = None  # type: ignore[assignment]
from werkzeug.middleware.proxy_fix import ProxyFix

from ai_ticket.events.inference import CompletionResponse, ErrorResponse, on_event
from ai_ticket.observability import metrics_store
from ai_ticket.runtime.diagnostics import run_diagnostics, simulate_request_lifecycle
from ai_ticket.ui import get_ui_dist_path
from ai_ticket.security import TokenManager, InMemoryRateLimiter, SQLiteRateLimiter


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


def _unregister_previous_metric_collectors(metric_names: list[str]) -> None:
    """Remove lingering collectors from the default Prometheus registry.

    When the server module is imported multiple times within the same Python
    process—as happens during the test suite—the global CollectorRegistry keeps
    the previously registered metrics. Re-registering the same metric names
    raises a ``ValueError`` about duplicate time series. Clearing the existing
    collectors first keeps the module import idempotent without requiring the
    caller to manage global Prometheus state.
    """

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

app = Flask(__name__)
trust_proxy_count = int(os.environ.get("TRUST_PROXY_COUNT", "0"))
if trust_proxy_count > 0:
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=trust_proxy_count,
        x_proto=trust_proxy_count,
        x_host=trust_proxy_count,
    )

EXEMPT_ENDPOINTS = {"health_check", "metrics", "diagnostics_self_test", "diagnostics_simulate"}


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

    if TOKEN_MANAGER.has_tokens():
        provided_token = _extract_bearer_token() or request.headers.get("X-API-Key")
        if not provided_token:
            logger.warning("Missing authentication token", extra={"path": request.path})
            return jsonify(
                {"error": "unauthorised", "details": "Authentication token missing."}
            ), 401

        if not TOKEN_MANAGER.is_valid(provided_token):
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
        metrics_store.record_event(
            latency_s=0.0,
            success=False,
            error_code="invalid_request",
            message="Request must be JSON.",
        )
        return jsonify({"error": "invalid_request", "details": "Request must be JSON."}), 400

    event_data = request.get_json()
    logger.info(
        "Received event data",
        extra={"keys": list(event_data.keys()) if isinstance(event_data, Mapping) else None},
    )

    start = perf_counter()

    try:
        response = on_event(event_data)
    except Exception as error:  # pragma: no cover - defensive guard
        duration = perf_counter() - start
        logger.exception("Unhandled exception processing event")
        metrics_store.record_event(
            latency_s=duration,
            success=False,
            error_code="unhandled_exception",
            message=str(error),
        )
        return jsonify({"error": "internal_error", "details": "An unexpected error occurred."}), 500

    duration = perf_counter() - start

    if isinstance(response, CompletionResponse):
        payload = asdict(response)
        logger.info("Successfully processed event", extra={"response_keys": list(payload.keys())})
        metrics_store.record_event(latency_s=duration, success=True)
        return jsonify(payload), 200

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
        return jsonify(payload), response.status_code

    payload = _normalise_response(response)
    status_code = payload.pop("status_code", 200)
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
    return jsonify(payload), status_code


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "shutdown_initiated": shutdown_event.is_set()}), 200


@app.route("/diagnostics/self-test", methods=["GET"])
def diagnostics_self_test():
    report = run_diagnostics()
    status_code = 200 if report.status != "error" else 503
    return jsonify(report.to_dict()), status_code


@app.route("/diagnostics/simulate", methods=["POST"])
def diagnostics_simulate():
    payload = request.get_json(silent=True) or {}
    event_payload: Mapping[str, Any] | None = None

    if isinstance(payload, Mapping):
        raw_event = payload.get("event")
        if raw_event is None:
            event_payload = None
        elif isinstance(raw_event, Mapping):
            event_payload = raw_event
        else:
            return jsonify({
                "status": "error",
                "error": "invalid_event_payload",
                "detail": "The 'event' field must be a mapping when provided.",
            }), 400
    else:
        return jsonify({
            "status": "error",
            "error": "invalid_payload",
            "detail": "Request body must be JSON.",
        }), 400

    simulation = simulate_request_lifecycle(
        token_manager=TOKEN_MANAGER,
        rate_limiter=RATE_LIMITER,
        event_payload=event_payload,
    )
    status_code = 200 if simulation.status != "error" else 503
    return jsonify(simulation.to_dict()), status_code


@app.route("/metrics", methods=["GET"])
def metrics() -> Response:
    return Response(generate_latest(), content_type=CONTENT_TYPE_LATEST)



@app.route("/api/metrics/summary", methods=["GET"])
def metrics_summary():
    return jsonify(metrics_store.snapshot()), 200


@app.route("/api/metrics/stream", methods=["GET"])
def metrics_stream():
    def event_stream():
        queue = metrics_store.subscribe()
        try:
            yield f"data: {metrics_store.snapshot_json()}\n\n"
            while True:
                payload = queue.get()
                yield f"data: {json.dumps(payload)}\n\n"
        finally:
            metrics_store.unsubscribe(queue)

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")


@app.route("/dashboard")
@app.route("/dashboard/<path:asset_path>")
def dashboard(asset_path: str | None = None):
    if not UI_DIST_PATH.exists():
        abort(404, description="Dashboard assets are not available. Build the UI bundle first.")

    resolved_path = UI_DIST_PATH / asset_path if asset_path else UI_DIST_PATH / "index.html"
    if asset_path and resolved_path.exists():
        return send_from_directory(str(UI_DIST_PATH), asset_path)

    return send_from_directory(str(UI_DIST_PATH), "index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
