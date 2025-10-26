import os
import signal
import time
from threading import Event
from typing import Any, Set

from flask import Flask, Response, g, jsonify, request
from werkzeug.exceptions import HTTPException

from ai_ticket.events.inference import on_event
from ai_ticket.metrics import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from ai_ticket.validation import BaseModel, ValidationError
import logging


class APIError(Exception):
    """Base class for application level errors with consistent JSON responses."""

    status_code: int = 400
    error: str = "bad_request"

    def __init__(self, details: Any = None, *, status_code: int | None = None, error: str | None = None) -> None:
        super().__init__(details)
        if status_code is not None:
            self.status_code = status_code
        if error is not None:
            self.error = error
        self.details = details


class RequestValidationError(APIError):
    error = "invalid_request"
    status_code = 400


class UnauthorizedError(APIError):
    error = "unauthorized"
    status_code = 401


class BackendServiceError(APIError):
    error = "backend_error"
    status_code = 502


class ServiceUnavailableError(APIError):
    error = "service_unavailable"
    status_code = 503


class EventRequest(BaseModel):
    """Schema that validates the shape of incoming /event requests."""

    content: Any

    class Config:
        extra = "allow"


# Configure logging
LOG_LEVEL_STR = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
log_level = LOG_LEVEL_MAP.get(LOG_LEVEL_STR, logging.INFO)
logging.basicConfig(level=log_level, format="%(asctime)s - %(levelname)s - %(message)s")

app = Flask(__name__)


REQUEST_COUNTER = Counter(
    "ai_ticket_http_requests_total",
    "Total number of HTTP requests processed.",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "ai_ticket_http_request_duration_seconds",
    "Duration of HTTP requests in seconds.",
    ["endpoint"],
)

AUTH_EXEMPT_ENDPOINTS: Set[str] = {
    "metrics",
    "health_check",
    "readiness_probe",
    "liveness_probe",
}

shutdown_event = Event()


def _parse_env_tokens(raw: str | None) -> Set[str]:
    if not raw:
        return set()
    return {token.strip() for token in raw.split(",") if token.strip()}


def _load_auth_tokens() -> Set[str]:
    return _parse_env_tokens(os.getenv("AI_TICKET_AUTH_TOKENS"))


def _load_api_keys() -> Set[str]:
    return _parse_env_tokens(os.getenv("AI_TICKET_API_KEYS"))


def _auth_header_name() -> str:
    return os.getenv("AI_TICKET_API_KEY_HEADER", "X-API-Key")


def _backend_error_status(error: str) -> int:
    return {
        "configuration_error": 500,
        "api_connection_error": 503,
        "api_response_format_error": 502,
        "api_response_structure_error": 502,
        "api_authentication_error": 502,
        "api_client_error": 400,
        "api_request_error": 502,
        "api_unknown_error": 502,
        "prompt_extraction_failed": 400,
        "missing_content_field": 400,
        "invalid_input_format": 400,
    }.get(error, 400)


def _readiness_reasons() -> list[str]:
    reasons: list[str] = []
    if shutdown_event.is_set():
        reasons.append("shutdown_in_progress")
    if not os.getenv("KOBOLDCPP_API_URL"):
        reasons.append("koboldcpp_api_url_not_configured")
    return reasons


def enforce_authentication() -> None:
    allowed_tokens = _load_auth_tokens()
    allowed_keys = _load_api_keys()
    if not allowed_tokens and not allowed_keys:
        return

    endpoint = request.endpoint or ""
    if endpoint in AUTH_EXEMPT_ENDPOINTS:
        return

    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:]

    api_key_header = _auth_header_name()
    api_key = request.headers.get(api_key_header, "")

    if (allowed_tokens and token in allowed_tokens) or (allowed_keys and api_key in allowed_keys):
        return

    logging.warning("Unauthorized request blocked for endpoint %s", endpoint)
    raise UnauthorizedError("A valid bearer token or API key is required.")


def register_error_handlers(flask_app: Flask) -> None:
    @flask_app.errorhandler(APIError)
    def handle_api_error(err: APIError):  # type: ignore[override]
        logging.error("APIError encountered: %s", err)
        payload = {"error": err.error}
        if err.details is not None:
            payload["details"] = err.details
        return jsonify(payload), err.status_code

    @flask_app.errorhandler(ValidationError)
    def handle_validation_error(err: ValidationError):  # type: ignore[override]
        logging.error("ValidationError encountered: %s", err)
        return (
            jsonify({"error": "invalid_request", "details": err.errors()}),
            400,
        )

    @flask_app.errorhandler(HTTPException)
    def handle_http_exception(err: HTTPException):  # type: ignore[override]
        logging.error("HTTPException encountered: %s", err)
        return jsonify({"error": err.name, "details": err.description}), err.code

    @flask_app.errorhandler(Exception)
    def handle_unexpected_error(err: Exception):  # type: ignore[override]
        logging.exception("Unexpected server error")
        return (
            jsonify({"error": "internal_server_error", "details": "An unexpected error occurred."}),
            500,
        )


def register_signal_handlers() -> None:
    def _handle_shutdown(signum: int, frame: Any) -> None:  # type: ignore[override]
        logging.info("Received shutdown signal %s. Marking worker as shutting down.", signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)


@app.before_request
def before_request() -> None:
    g.request_start_time = time.time()
    enforce_authentication()


@app.after_request
def after_request(response):
    endpoint = request.endpoint or "unknown"
    duration = None
    if hasattr(g, "request_start_time"):
        duration = time.time() - g.request_start_time
    REQUEST_COUNTER.labels(request.method, endpoint, str(response.status_code)).inc()
    if duration is not None:
        REQUEST_LATENCY.labels(endpoint).observe(duration)
    return response


@app.route("/event", methods=["POST"])
def handle_event():
    if not request.is_json:
        logging.error("Request is not JSON")
        raise RequestValidationError("Request must be JSON.")

    raw_event = request.get_json()
    if not isinstance(raw_event, dict):
        raise RequestValidationError("Request JSON must be an object.")
    logging.debug("Raw event payload: %s", raw_event)

    try:
        validated_event = EventRequest(**raw_event)
    except ValidationError as err:
        raise RequestValidationError(err.errors()) from err

    logging.info("Received event data after validation: %s", validated_event.dict())

    response = on_event(validated_event.dict())

    if "error" in response:
        error_code = response.get("error", "backend_error")
        status_code = _backend_error_status(error_code)
        logging.error("Error processing event: %s", response)
        raise BackendServiceError(
            response.get("details", "The backend reported an error."),
            status_code=status_code,
            error=error_code,
        )

    logging.info("Successfully processed event, response: %s", response)
    return jsonify(response), 200


@app.route("/metrics", methods=["GET"])
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.route("/health", methods=["GET"])
@app.route("/healthz", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "timestamp": int(time.time())}), 200


@app.route("/readyz", methods=["GET"])
def readiness_probe():
    reasons = _readiness_reasons()
    if reasons:
        raise ServiceUnavailableError({"reasons": reasons})
    return jsonify({"status": "ready"}), 200


@app.route("/livez", methods=["GET"])
def liveness_probe():
    if shutdown_event.is_set():
        raise ServiceUnavailableError("Shutdown in progress.")
    return jsonify({"status": "live"}), 200


register_error_handlers(app)
register_signal_handlers()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
