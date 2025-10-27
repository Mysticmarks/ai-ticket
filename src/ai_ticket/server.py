from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, is_dataclass
from time import perf_counter
from typing import Any, Mapping

from flask import Flask, Response, abort, jsonify, request, send_from_directory
from flask import stream_with_context

from ai_ticket.events.inference import CompletionResponse, ErrorResponse, on_event
from ai_ticket.observability import metrics_store
from ai_ticket.ui import get_ui_dist_path


logger = logging.getLogger(__name__)

UI_DIST_PATH = get_ui_dist_path()

app = Flask(__name__)

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
    logger.info("Received event data", extra={"keys": list(event_data.keys()) if isinstance(event_data, Mapping) else None})

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
    return jsonify({"status": "healthy"}), 200


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
    # Make sure to run with host='0.0.0.0' to be accessible from outside the container
    app.run(host="0.0.0.0", port=port)


def _normalise_response(response: Any) -> dict[str, Any]:
    if is_dataclass(response):
        return asdict(response)
    if isinstance(response, Mapping):
        return dict(response)
    return {"result": response}
