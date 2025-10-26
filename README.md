# ai-ticket
[![CI Status](https://github.com/jmikedupont2/ai-ticket/actions/workflows/ci.yml/badge.svg)](https://github.com/jmikedupont2/ai-ticket/actions/workflows/ci.yml) [![codecov](https://codecov.io/gh/jmikedupont2/ai-ticket/branch/docker-main/graph/badge.svg)](https://codecov.io/gh/jmikedupont2/ai-ticket) [![Linting: Flake8](https://img.shields.io/badge/linting-flake8-blue.svg)](https://flake8.pycqa.org/) [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black) [![Imports: isort](https://img.shields.io/badge/%20imports-isort-%231674b1?style=flat&labelColor=ef8336)](https://pycqa.github.io/isort/)

The AI Ticket system is designed to streamline interactions with Large Language Models (LLMs), with a primary focus on the KoboldCPP backend. It acts as a robust intermediary, processing event-based requests, managing communication with the LLM, and returning structured responses, including comprehensive error handling.

* Join us on Discord: https://discord.com/invite/XWSam9kE (Note: Link may become outdated)

## Project Overview

`ai-ticket` is a Python-based application that simplifies interaction with LLMs by:

*   **Receiving Event Data**: Accepts requests containing prompts, typically as JSON payloads.
*   **Prompt Extraction**: Intelligently extracts or constructs a usable prompt from the input event data.
*   **KoboldCPP Interaction**: Sends the prompt to a configured KoboldCPP-compatible API. It includes features like:
    *   **Endpoint Fallback**: Tries OpenAI-compatible chat completion endpoints first, then falls back to standard completion endpoints.
    *   **Retry Mechanisms**: Automatically retries requests on transient network issues (ConnectionError, Timeout) and specific HTTP errors (5xx, 429 Too Many Requests) with exponential backoff.
*   **Structured Responses**: Returns either a successful completion or a standardized error message.
*   **Containerized Deployment**: Utilizes Docker and Docker Compose for easy deployment and scaling.
*   **CI/CD**: Includes GitHub Actions workflows for continuous integration (linting, testing, coverage reporting, building) and Docker image publishing.

The system is built to be resilient and provide clear feedback, making it a reliable component for integrating LLM capabilities into larger applications.

## Architecture

The system comprises several key components:

*   **`ai-ticket` Python Package (`src/ai_ticket/`)**:
    *   `events/inference.py`: Contains the main `on_event` function. This function is the primary entry point for interacting with the system. It handles input validation, prompt extraction, calls the KoboldCPP client, and formats the final response (either completion or error).
    *   `backends/kobold_client.py`: Provides the `get_kobold_completion` function responsible for all communication with the KoboldCPP API. It implements retry logic, endpoint fallback, and detailed error categorization.
    *   `server.py`: The Flask application server, providing the HTTP interface (e.g., `/event`). It now layers request validation, authentication middleware, centralized error handling, Prometheus metrics, and operational probes (`/healthz`, `/readyz`, `/livez`).
    *   `find_name.py`: A utility function to extract a name (e.g., an AI agent's name) from a structured text block. (Currently less central but available).
*   **Docker Service (`docker-compose.yml` and `Dockerfile`)**:
    *   `ai_ticket`: The main application service, built from the local `Dockerfile`. It's configured for resilience (e.g., `restart: unless-stopped`) and uses Gunicorn as the WSGI server.
    *   **Health Check**: The Docker container is configured with a health check (via the `HEALTHCHECK` instruction in the `Dockerfile` and corresponding settings in `docker-compose.yml`) that periodically queries the `/health` endpoint to ensure the application is running correctly.
*   **Configuration (Environment Variables)**:
    *   `KOBOLDCPP_API_URL`: Specifies the KoboldCPP API endpoint. (Default: `http://localhost:5001/api` if not set, though providing it explicitly is recommended).
    *   `LOG_LEVEL`: Sets the application's logging level (e.g., `DEBUG`, `INFO`, `WARNING`). (Default: `INFO`).
    *   `AI_TICKET_AUTH_TOKENS`: Optional comma-separated list of bearer tokens. When provided, every request (except metrics and health probes) must send one of these tokens via the `Authorization: Bearer <token>` header.
    *   `AI_TICKET_API_KEYS`: Optional comma-separated list of API keys accepted via a custom header (defaults to `X-API-Key`).
    *   `AI_TICKET_API_KEY_HEADER`: Optional header name to use when validating API keys. Defaults to `X-API-Key`.
    *   `PORT`: Overrides the default listen port (`5000`) when running the Flask development server directly.
*   **GitHub Actions Workflows (`.github/workflows/`)**:
    *   `ci.yml`: Continuous Integration – Lints, tests (with code coverage reporting to Codecov), validates `docker-compose.yml`, and builds the `ai_ticket` Docker image.
    *   `docker-image.yml`: Docker Image Publishing – Builds and pushes the `ai_ticket` image to Docker Hub.
    *   `run.yml`: Manual Application Run – Allows manual triggering to run the application using `docker-compose` with pre-built images.
    *   `static.yml`: Static Page Deployment – Deploys content from the `pyre` branch to GitHub Pages (user should verify content of `pyre` branch).
*   **Submodules & the `vendor/` Directory**:
    *   This project has significantly simplified its structure by **removing all previously included Git submodules**. As such, fresh clones of this repository will not include any submodules, and the `vendor/` directory (which previously housed them) will not be present.
    *   If you have an older local clone of this repository, you might still see directories like `vendor/lollms`, `vendor/Auto-GPT`, `vendor/openai-python`, etc. These are remnants of the old submodule structure, are **no longer tracked by Git**, and are not used by the application.
    *   You can safely delete the entire `vendor/` directory from your local workspace to avoid confusion and align with the current project structure.
    *   This cleanup streamlines the project, reduces clutter, and clarifies that the core functionality does not depend on these external repositories. The project currently uses **no Git submodules**.

## Error Handling

The `ai-ticket` system uses a standardized error response format for operations initiated via `on_event`:

```json
{
  "error": "error_code_string",
  "details": "A human-readable message explaining the error."
}
```

Key `error_code`s include:

*   **Input Validation Errors (from `on_event`):**
    *   `invalid_input_format`: Event data was not a dictionary.
    *   `missing_content_field`: The required 'content' field was missing in the event data.
    *   `prompt_extraction_failed`: Could not derive a usable string prompt from the 'content' field.
*   **KoboldCPP Client Errors (from `get_kobold_completion`):**
    *   `configuration_error`: `KOBOLDCPP_API_URL` environment variable is not set.
    *   `api_connection_error`: Failed to connect to the KoboldCPP API after multiple retries (due to connection errors, timeouts, or 5xx server errors).
    *   `api_authentication_error`: Request failed due to authentication/authorization issues (HTTP 401, 403).
    *   `api_client_error`: Request failed due to other client-side errors (other HTTP 4xx errors, excluding 429).
    *   `api_response_format_error`: Failed to decode the JSON response from the KoboldCPP API.
    *   `api_response_structure_error`: The JSON response from KoboldCPP was valid but did not match the expected structure (e.g., missing `choices[0].message.content`).
    *   `api_request_error`: An unexpected error occurred during the HTTP request itself (not covered by more specific exceptions).
    *   `api_unknown_error`: All attempts to contact the API failed without a more specific categorized error.

The `kobold_client` automatically retries requests that fail due to transient issues like network connection errors, timeouts, or HTTP 5xx server errors, using an exponential backoff strategy. For HTTP 429 (Too Many Requests), it respects the `Retry-After` header if provided.

## Prerequisites

*   **Git**: For cloning the repository.
*   **Python**: Version 3.10 (as specified in `Dockerfile` and CI).
*   **Docker**: For building and running the application via `docker-compose`.
*   **Docker Compose**: For orchestrating the `ai_ticket` container.
*   **KoboldCPP Instance**: A running instance of KoboldCPP (or a compatible API) accessible to the `ai_ticket` service.

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/jmikedupont2/ai-ticket.git
cd ai-ticket
```
*(Note: This project no longer uses Git submodules, so commands like `git submodule update --init --recursive` are not needed.)*

### 2. Configure Environment Variables

The `ai_ticket` service is configured via environment variables. For local execution (including Docker Compose), it's recommended to create an `.env` file in the project root:

```env
KOBOLDCPP_API_URL=http://your-koboldcpp-host:5001/api
LOG_LEVEL=INFO
```

*   **`KOBOLDCPP_API_URL`** (Required): The full URL to your KoboldCPP API endpoint.
    *   Replace `http://your-koboldcpp-host:5001/api` with the actual URL.
    *   If KoboldCPP is running on your host machine and you are using Docker Desktop, you might use `http://host.docker.internal:5001/api`.
    *   The application defaults to `http://localhost:5001/api` if this variable is not set, but explicitly setting it is highly recommended.
*   **`LOG_LEVEL`** (Optional): Sets the application's logging verbosity.
    *   Options: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.
    *   Default: `INFO`.

This configuration is crucial for the application to function correctly. If not using an `.env` file, ensure these variables are exported in your shell environment.

### 3. Local Development Setup (Optional)

For development outside of Docker:

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
```

Install dependencies:
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt # For linting, testing, etc.
```

Install the `ai_ticket` package in editable mode:
```bash
pip install -e .
```
Remember to set the `KOBOLDCPP_API_URL` environment variable in your shell.

## Running the Application

The primary method for running the system is using Docker Compose. The application runs inside the Docker container using **Gunicorn** as the WSGI server, which provides a robust way to handle concurrent requests.

1.  **Environment Variables**:
    *   **`KOBOLDCPP_API_URL`** (Required): Ensure this environment variable is available in your shell or in an `.env` file in the project root. This variable is crucial for the application to connect to your KoboldCPP instance. See the "Getting Started" section for more details on setting this up.
        Example value: `http://host.docker.internal:5001/api`
    *   **`LOG_LEVEL`** (Optional): Set this to configure the application's logging verbosity. Valid values are `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Defaults to `INFO`.
        Example value: `DEBUG`

    You can create an `.env` file in the project root to manage these:
    ```env
    KOBOLDCPP_API_URL=http://host.docker.internal:5001/api
    LOG_LEVEL=INFO
    ```

2.  **Start the Service**:
    ```bash
    docker-compose up --build
    ```
    The `--build` flag ensures the image is built with any local changes. For subsequent runs, you can omit it if the image hasn't changed.
    The service, running with Gunicorn, will now be listening for POST requests on `http://localhost:5000/event` and health checks on `http://localhost:5000/health`.

3.  **Run in Detached Mode**:
    ```bash
    docker-compose up -d
    ```
    The service will now be listening for POST requests on `http://localhost:5000/event`.

4.  **View Logs**:
    ```bash
    docker-compose logs -f ai_ticket
    ```

5.  **Stop the Services**:
    ```bash
    docker-compose down
    ```

The `ai_ticket` service, once running, exposes an HTTP endpoint to receive events.

## Observability and Operational Readiness

The Flask server layers several operational concerns on top of the business logic:

*   **Request Validation** – Incoming payloads are validated with [Pydantic](https://docs.pydantic.dev/). Invalid payloads are rejected with a structured error before they reach the event handler.
*   **Authentication Middleware** – When either `AI_TICKET_AUTH_TOKENS` or `AI_TICKET_API_KEYS` is set, every request to application endpoints must present a matching bearer token (`Authorization: Bearer <token>`) or API key (header defaults to `X-API-Key`). Health, liveness, readiness, and metrics endpoints remain publicly accessible for infrastructure probes.
*   **Centralized Error Handling** – All exceptions are normalized into the `{ "error": ..., "details": ... }` envelope, making it easy for clients to reason about failures.
*   **Metrics** – Prometheus counters and histograms are exposed on `/metrics`, instrumenting request totals and latencies by endpoint. You can scrape this endpoint directly or via an existing Prometheus Operator.
*   **Probes** –
    *   `GET /healthz` (alias `/health`) reports general service health.
    *   `GET /readyz` surfaces readiness issues. It fails with `503` if required configuration is missing or if a shutdown has been requested.
    *   `GET /livez` stays healthy while the worker is alive and not terminating.
*   **Graceful Shutdown** – Gunicorn workers trap `SIGTERM`/`SIGINT`, mark themselves as shutting down, and cause `/livez`/`/readyz` to fail so that load balancers stop routing traffic before the worker exits.

## Deployment Configuration Examples

The following snippets demonstrate how to configure the new middleware, probes, and metrics in common deployment scenarios.

### Docker Compose

```yaml
services:
  ai_ticket:
    build: .
    environment:
      KOBOLDCPP_API_URL: "http://koboldcpp:5001/api"
      LOG_LEVEL: "INFO"
      AI_TICKET_AUTH_TOKENS: "local-dev-token"
      AI_TICKET_API_KEYS: "service-key-1,service-key-2"
      AI_TICKET_API_KEY_HEADER: "X-Custom-Api-Key"
    ports:
      - "5000:5000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
    command: >-
      gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 src.ai_ticket.server:app
```

### Helm Values Snippet

```yaml
env:
  KOBOLDCPP_API_URL: "http://koboldcpp.default.svc.cluster.local:5001/api"
  LOG_LEVEL: "INFO"
  AI_TICKET_AUTH_TOKENS: "prod-token-1,prod-token-2"
  AI_TICKET_API_KEYS: "team-a-key,team-b-key"
livenessProbe:
  httpGet:
    path: /livez
    port: http
  initialDelaySeconds: 10
  periodSeconds: 15
readinessProbe:
  httpGet:
    path: /readyz
    port: http
  initialDelaySeconds: 10
  periodSeconds: 15
metrics:
  serviceMonitor:
    enabled: true
    endpoints:
      - path: /metrics
        interval: 30s
```

These examples assume your Helm chart exposes generic `env`, `livenessProbe`, and `readinessProbe` values and optionally integrates with the Prometheus Operator via `ServiceMonitor` resources. Adjust field names to match your chart.

## Examples
The `ai_ticket` service now exposes an HTTP endpoint to receive events. You can send a POST request with a JSON payload to `http://localhost:5000/event` when the service is running via Docker Compose.

Here's an example using `curl`:
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"content": "Explain gravity to a five-year-old."}' \
     http://localhost:5000/event
```

The following Python examples demonstrate the direct usage of the `on_event` function, which is the core logic behind the HTTP endpoint. While you can use `on_event` directly if you integrate `ai_ticket` as a Python library, the primary interaction method for the deployed service is via the HTTP endpoint described above.

```python
import json
from ai_ticket.events.inference import on_event # Assuming your Python path is set up

# Example 1: Simple text prompt
event_data_simple = {
    "content": "Explain the theory of relativity in simple terms."
}

response_simple = on_event(event_data_simple)

if "completion" in response_simple:
    print(f"LLM Response (Simple): {response_simple['completion']}")
elif "error" in response_simple:
    print(f"Error (Simple): {response_simple['error']} - {response_simple.get('details', '')}")

# Example 2: OpenAI-style chat messages in JSON string
event_data_chat_json = {
    "content": json.dumps({
        "messages": [
            {"role": "user", "content": "What are the benefits of using Docker?"}
        ],
        # "model": "custom_model_if_needed_by_backend", # For Kobold, model is fixed in client
        # "max_tokens": 100 # These would be handled by kobold_client defaults or params
    })
}

response_chat_json = on_event(event_data_chat_json)

if "completion" in response_chat_json:
    print(f"LLM Response (Chat JSON): {response_chat_json['completion']}")
elif "error" in response_chat_json:
    print(f"Error (Chat JSON): {response_chat_json['error']} - {response_chat_json.get('details', '')}")

# Example 3: Input validation error
event_data_invalid = {
    "wrong_key": "This will cause an error"
}
response_invalid = on_event(event_data_invalid)
if "error" in response_invalid:
    print(f"Error (Invalid Input): {response_invalid['error']} - {response_invalid.get('details', '')}")

# Example of how find_name might be used (less central now)
from ai_ticket import find_name
long_json_like_string = """{"name": "MyAgent", "details": {...}}""" # Simplified
agent_name = find_name(long_json_like_string)
if agent_name:
    print(f"Extracted Name: {agent_name}")

```

## Troubleshooting

*   **`KOBOLDCPP_API_URL` Not Set / Incorrect**:
    *   **Symptom**: Errors like `{"error": "configuration_error", ...}` or connection failures.
    *   **Solution**: Ensure `KOBOLDCPP_API_URL` is correctly set in your environment (e.g., via `export` or in an `.env` file as described in "Getting Started") and points to your running KoboldCPP instance's API endpoint (typically ending in `/api`).
*   **Logging Configuration**:
    *   **Symptom**: Logs are too verbose or not detailed enough.
    *   **Solution**: Adjust the `LOG_LEVEL` environment variable. Set it to `DEBUG` for more detailed output when troubleshooting, or to `WARNING` or `ERROR` for less verbose logs in production. Default is `INFO`.
*   **KoboldCPP Connection Issues (`api_connection_error`)**:
    *   Ensure your KoboldCPP instance is running and accessible from where `ai_ticket` is running (your host machine for local dev, or from within the Docker container).
    *   Verify the `KOBOLDCPP_API_URL` is correct.
    *   If running `ai_ticket` in Docker and KoboldCPP on the host, use `http://host.docker.internal:PORT/api` (for Docker Desktop) or your host's actual IP address if Docker is configured differently.
    *   Check KoboldCPP logs for any errors on its side.
    *   Firewall issues might be blocking the connection.
*   **Authentication Errors (`api_authentication_error`)**:
    *   This indicates that the KoboldCPP instance requires authentication, and `ai_ticket` is not configured for it (currently, it doesn't support passing auth tokens). Ensure your KoboldCPP API is accessible without authentication if you intend to use it with `ai_ticket` as is.
*   **Submodule Issues**:
    *   This project no longer uses Git submodules. If you have an old clone of the repository, you might want to ensure your working directory is clean (e.g., by running `git clean -fdx` in the `vendor` directory if it still exists and you're sure you don't need its contents, or by starting with a fresh clone).
*   **Docker Build Failures**:
    *   Check Docker daemon status and internet connectivity.
    *   Examine build logs for specific error messages (e.g., dependency installation failures).
*   **Python Dependency Conflicts (Local Development)**:
    *   Ensure your virtual environment is activated.
    *   Try reinstalling dependencies: `pip install -r requirements.txt -r requirements-dev.txt`.

## Workflows

The project utilizes several GitHub Actions workflows:

*   **`ci.yml` (Continuous Integration)**:
    *   Triggered on pushes and pull requests to the `docker-main` branch.
    *   Performs:
        *   Checkout repository (including submodules).
        *   Set up Python.
        *   Dependency installation (`requirements.txt`, `requirements-dev.txt`, `pytest-cov`).
        *   Validation of `docker-compose.yml` syntax (`docker-compose config -q`).
        *   Linting with `flake8`.
        *   Format checking with `black` and `isort`.
        *   Running tests with `pytest`, generating a coverage report (`coverage.xml`).
        *   Uploading coverage report to Codecov.
        *   Building the `ai_ticket` Docker image to ensure it's valid.
*   **`docker-image.yml` (Docker Image Publishing)**:
    *   Triggered on pushes to the `docker-main` branch (typically after merging) and can be manually dispatched.
    *   Builds the `ai_ticket` Docker image and pushes it to Docker Hub (e.g., `jmikedupont2/ai-ticket`), tagged with `latest` and the commit SHA.
*   **`run.yml` (Run Application)**:
    *   Manually triggered workflow (`workflow_dispatch`).
    *   Checks out the repository.
    *   Runs `docker-compose -f docker-compose-run.yml up --no-build` to start the `ai_ticket` service using the pre-built image and configurations specified in `docker-compose-run.yml` (which typically points to an image on Docker Hub). This is useful for quick deployments or testing of a specific image version.
*   **`static.yml` (Static Pages Deployment)**:
    *   Triggered on pushes to the `pyre` branch or manually.
    *   Deploys content from the `pyre` branch to GitHub Pages.
    *   **Note**: The user should verify the content and purpose of the `pyre` branch. The workflow currently uploads the entire repository content from that branch (`path: '.'`). This should be changed to a specific build output directory (e.g., `docs/_site/`) if a static site generator is used.

## Contributing

Contributions are welcome! Please follow these steps:

1.  Fork the repository.
2.  Create a new branch for your feature or bug fix.
3.  Make your changes.
4.  Ensure your code lints and formats correctly (`flake8 .`, `black .`, `isort .`).
5.  Run tests and ensure they pass (`pytest tests/`).
6.  Commit your changes with clear messages.
7.  Push your branch to your fork.
8.  Create a Pull Request against the `docker-main` branch of the original repository.
9.  Ensure CI checks pass on your Pull Request.

---
*This README has been significantly updated to reflect current project structure and functionality.*
