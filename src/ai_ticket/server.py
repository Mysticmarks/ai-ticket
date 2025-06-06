import os
from flask import Flask, request, jsonify
from ai_ticket.events.inference import on_event
import logging

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
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

@app.route("/event", methods=["POST"])
def handle_event():
    if not request.is_json:
        logging.error("Request is not JSON")
        return jsonify({"error": "invalid_request", "details": "Request must be JSON."}), 400

    event_data = request.get_json()
    logging.info(f"Received event data: {event_data}")

    response = on_event(event_data)

    if "error" in response:
        logging.error(f"Error processing event: {response}")
        # Determine status code based on error type if possible, otherwise default
        status_code = 400 # Default for client-side errors
        if response.get("error") == "configuration_error":
            status_code = 500
        elif response.get("error") == "api_connection_error":
            status_code = 503 # Service Unavailable
        # Add more specific error to status_code mappings if needed
        return jsonify(response), status_code

    logging.info(f"Successfully processed event, response: {response}")
    return jsonify(response), 200

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Make sure to run with host='0.0.0.0' to be accessible from outside the container
    app.run(host="0.0.0.0", port=port)
