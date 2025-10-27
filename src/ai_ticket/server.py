from __future__ import annotations

import os
import logging
import time
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from flask import Flask, jsonify, request

from ai_ticket.events.inference import CompletionResponse, ErrorResponse, on_event
from ai_ticket.telemetry import Status, StatusCode, get_meter, get_tracer


logger = logging.getLogger(__name__)

app = Flask(__name__)

_TRACER = get_tracer(__name__)
_METER = get_meter(__name__)

_REQUEST_COUNTER = _METER.create_counter(
    "ai_ticket_server_requests_total",
    description="Total number of requests handled by the Flask server.",
)
_REQUEST_FAILURES = _METER.create_counter(
    "ai_ticket_server_request_failures_total",
    description="Total number of server requests that resulted in an error response.",
)
_REQUEST_LATENCY = _METER.create_histogram(
    "ai_ticket_server_request_duration_seconds",
    unit="s",
    description="Duration of Flask request handling.",
)

_HEALTH_COUNTER = _METER.create_counter(
    "ai_ticket_server_health_checks_total",
    description="Count of health check requests handled.",
)
_HEALTH_LATENCY = _METER.create_histogram(
    "ai_ticket_server_health_check_duration_seconds",
    unit="s",
    description="Duration of health check handling.",
)

@app.route("/event", methods=["POST"])
def handle_event():
    attributes = {"http.route": "/event", "http.method": request.method}
    _REQUEST_COUNTER.add(1, attributes)
    start = time.perf_counter()
    status_label = "UNSET"

    with _TRACER.start_as_current_span("server.handle_event") as span:
        span.set_attributes(attributes)
        try:
            if not request.is_json:
                logger.error("Request is not JSON")
                span.set_status(Status(StatusCode.ERROR, "invalid_request"))
                _REQUEST_FAILURES.add(1, {**attributes, "error": "invalid_request"})
                status_label = "ERROR"
                return (
                    jsonify({"error": "invalid_request", "details": "Request must be JSON."}),
                    400,
                )

            event_data = request.get_json()
            payload_keys = list(event_data.keys()) if isinstance(event_data, Mapping) else None
            span.set_attribute("request.payload_keys", payload_keys)
            logger.info("Received event data", extra={"keys": payload_keys})

            response = on_event(event_data)

            if isinstance(response, CompletionResponse):
                payload = asdict(response)
                span.set_status(Status(StatusCode.OK))
                status_label = "OK"
                logger.info("Successfully processed event", extra={"response_keys": list(payload.keys())})
                return jsonify(payload), 200

            if isinstance(response, ErrorResponse):
                payload = asdict(response)
                span.set_status(Status(StatusCode.ERROR, response.error))
                _REQUEST_FAILURES.add(1, {**attributes, "error": response.error})
                status_label = "ERROR"
                logger.error(
                    "Error processing event",
                    extra={"error_code": response.error, "status_code": response.status_code},
                )
                return jsonify(payload), response.status_code

            payload = _normalise_response(response)
            status_code = payload.pop("status_code", 200)
            if status_code >= 400 or payload.get("error"):
                error_code = payload.get("error", "unknown")
                span.set_status(Status(StatusCode.ERROR, error_code))
                _REQUEST_FAILURES.add(1, {**attributes, "error": error_code})
                status_label = "ERROR"
                logger.error("Processing event returned legacy error", extra={"payload": payload})
            else:
                span.set_status(Status(StatusCode.OK))
                status_label = "OK"
            return jsonify(payload), status_code
        except Exception as exc:  # pragma: no cover - defensive telemetry hook
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            _REQUEST_FAILURES.add(1, {**attributes, "error": "exception"})
            status_label = "ERROR"
            raise
        finally:
            duration = time.perf_counter() - start
            _REQUEST_LATENCY.record(duration, {**attributes, "status": status_label})

@app.route("/health", methods=["GET"])
def health_check():
    attributes = {"http.route": "/health", "http.method": request.method}
    _HEALTH_COUNTER.add(1, attributes)
    start = time.perf_counter()
    status_label = "OK"

    with _TRACER.start_as_current_span("server.health_check") as span:
        span.set_attributes(attributes)
        span.set_status(Status(StatusCode.OK))
        response = jsonify({"status": "healthy"})
        duration = time.perf_counter() - start
        _HEALTH_LATENCY.record(duration, {**attributes, "status": status_label})
        return response, 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Make sure to run with host='0.0.0.0' to be accessible from outside the container
    app.run(host="0.0.0.0", port=port)


def _normalise_response(response: Any) -> dict[str, Any]:
    if is_dataclass(response):
        return asdict(response)
    if isinstance(response, Mapping):
        return dict(response)
    return {"result": response}
