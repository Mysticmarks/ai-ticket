from __future__ import annotations

import os
import logging
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from flask import Flask, jsonify, request

from ai_ticket.events.inference import CompletionResponse, ErrorResponse, on_event


logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route("/event", methods=["POST"])
def handle_event():
    if not request.is_json:
        logger.error("Request is not JSON")
        return jsonify({"error": "invalid_request", "details": "Request must be JSON."}), 400

    event_data = request.get_json()
    logger.info("Received event data", extra={"keys": list(event_data.keys()) if isinstance(event_data, Mapping) else None})

    response = on_event(event_data)

    if isinstance(response, CompletionResponse):
        payload = asdict(response)
        logger.info("Successfully processed event", extra={"response_keys": list(payload.keys())})
        return jsonify(payload), 200

    if isinstance(response, ErrorResponse):
        payload = asdict(response)
        logger.error("Error processing event", extra={"error_code": response.error, "status_code": response.status_code})
        return jsonify(payload), response.status_code

    payload = _normalise_response(response)
    status_code = payload.pop("status_code", 200)
    if payload.get("error"):
        logger.error("Processing event returned legacy error", extra={"payload": payload})
    return jsonify(payload), status_code

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy"}), 200

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
