# ai-ticket
[![CI Status](https://github.com/jmikedupont2/ai-ticket/actions/workflows/ci.yml/badge.svg)](https://github.com/jmikedupont2/ai-ticket/actions/workflows/ci.yml) [![codecov](https://codecov.io/gh/jmikedupont2/ai-ticket/branch/docker-main/graph/badge.svg)](https://codecov.io/gh/jmikedupont2/ai-ticket) [![Linting: Flake8](https://img.shields.io/badge/linting-flake8-blue.svg)](https://flake8.pycqa.org/)

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
    *   `find_name.py`: A utility function to extract a name (e.g., an AI agent's name) from a structured text block. (Currently less central but available).
*   **Docker Service (`docker-compose.yml`)**:
    *   `ai_ticket`: The main application service, built from the local `Dockerfile`. It's configured for resilience (e.g., `restart: unless-stopped`).
*   **Configuration**:
    *   `KOBOLDCPP_API_URL`: Environment variable to specify the KoboldCPP API endpoint.
*   **GitHub Actions Workflows (`.github/workflows/`)**:
    *   `ci.yml`: Continuous Integration – Lints, tests (with code coverage reporting to Codecov), validates `docker-compose.yml`, and builds the `ai_ticket` Docker image.
    *   `docker-image.yml`: Docker Image Publishing – Builds and pushes the `ai_ticket` image to Docker Hub.
    *   `run.yml`: Manual Application Run – Allows manual triggering to run the application using `docker-compose` with pre-built images.
    *   `static.yml`: Static Page Deployment – Deploys content from the `pyre` branch to GitHub Pages (user should verify content of `pyre` branch).
*   **Submodules**:
    *   The project previously used submodules like `vendor/Auto-GPT` and `vendor/openai-python`, but these have been **removed** to streamline focus on the core KoboldCPP interaction.
    *   Remaining submodules like `vendor/lollms`, `vendor/Auto-GPT-Plugin-Template`, and `vendor/Auto-GPT-Benchmarks` are included for potential future utility or reference but are **not actively used** by the core `ai_ticket` application.

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
# Initialize and update any remaining relevant submodules (currently none are critical for core functionality)
git submodule update --init --recursive
```
*(Note: After recent cleanup, core functionality does not depend on specific submodules like Auto-GPT or openai-python, which have been removed.)*

### 2. Configure KoboldCPP API Access

The `ai_ticket` service needs to connect to a KoboldCPP API.
*   **Environment Variable**: Set the `KOBOLDCPP_API_URL` environment variable.
    *   Example: `export KOBOLDCPP_API_URL="http://localhost:5001/api"`
    *   If your KoboldCPP instance is running on your host machine and you are using Docker Desktop, you might use `http://host.docker.internal:5001/api`.
*   **Default**: If the variable is not set, the system defaults to `http://localhost:5001/api`.

This URL is crucial for the application to function.

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

The primary method for running the system is using Docker Compose.

1.  **Ensure `KOBOLDCPP_API_URL` is Set**: Make sure this environment variable is available in your shell or in an `.env` file in the project root (this file is gitignored).
    Example `.env` file content:
    ```
    KOBOLDCPP_API_URL=http://host.docker.internal:5001/api
    ```

2.  **Start the Service**:
    ```bash
    docker-compose up --build
    ```
    The `--build` flag ensures the image is built with any local changes. For subsequent runs, you can omit it if the image hasn't changed.

3.  **Run in Detached Mode**:
    ```bash
    docker-compose up -d
    ```

4.  **View Logs**:
    ```bash
    docker-compose logs -f ai_ticket
    ```

5.  **Stop the Services**:
    ```bash
    docker-compose down
    ```

The `ai_ticket` service, once running, will process events. The exact mechanism for sending events to it (e.g., an HTTP endpoint if exposed by the Python application, or another message queue) depends on how the `ENTRYPOINT` or `CMD` in the `Dockerfile` is configured to run the Python application. The current setup implies the Python application itself would need to implement the listening mechanism (e.g., a simple web server).

## Examples

The main way to interact with the `ai-ticket` system programmatically (if you were importing it as a Python library, or for testing) is via its `on_event` function.

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
    *   **Solution**: Ensure `KOBOLDCPP_API_URL` is correctly set in your environment (e.g., via `export` or in an `.env` file) and points to your running KoboldCPP instance's API endpoint (typically ending in `/api`).
*   **KoboldCPP Connection Issues (`api_connection_error`)**:
    *   Ensure your KoboldCPP instance is running and accessible from where `ai_ticket` is running (your host machine for local dev, or from within the Docker container).
    *   Verify the `KOBOLDCPP_API_URL` is correct.
    *   If running `ai_ticket` in Docker and KoboldCPP on the host, use `http://host.docker.internal:PORT/api` (for Docker Desktop) or your host's actual IP address if Docker is configured differently.
    *   Check KoboldCPP logs for any errors on its side.
    *   Firewall issues might be blocking the connection.
*   **Authentication Errors (`api_authentication_error`)**:
    *   This indicates that the KoboldCPP instance requires authentication, and `ai_ticket` is not configured for it (currently, it doesn't support passing auth tokens). Ensure your KoboldCPP API is accessible without authentication if you intend to use it with `ai_ticket` as is.
*   **Submodule Issues (General)**:
    *   If you encounter issues related to submodules (though core functionality no longer relies on the removed ones), ensure they are correctly initialized: `git submodule update --init --recursive`.
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
    *   Runs `docker-compose up --no-build` to start the `ai_ticket` service using pre-built images (as defined in `docker-compose-run.yml`, which typically points to an image on Docker Hub). This is useful for quick deployments or testing of a specific image version.
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
