# ai-ticket
[![CI Status](https://github.com/jmikedupont2/ai-ticket/actions/workflows/ci.yml/badge.svg)](https://github.com/jmikedupont2/ai-ticket/actions/workflows/ci.yml) [![codecov](https://codecov.io/gh/jmikedupont2/ai-ticket/branch/docker-main/graph/badge.svg)](https://codecov.io/gh/jmikedupont2/ai-ticket) [![Linting: Flake8](https://img.shields.io/badge/linting-flake8-blue.svg)](https://flake8.pycqa.org/)

The AI Ticket system to handle the AI with tickets. Human Powered AI-Ops to Help you with the last mile of your AI code generated system.

* Join us on discord https://discord.com/invite/XWSam9kE

## Project Overview

ai-ticket is a Python-based system designed to facilitate interactions with AI models. It processes events, extracts prompts, and interacts with a configurable Large Language Model (LLM) backend, currently focused on KoboldCPP. The system uses a ticket-based metaphor where user or system queries can be handled as discrete units. It leverages Docker for containerization and includes CI/CD workflows for testing and building.

The system is designed to:
- Receive event data containing prompts (either directly or embedded in JSON).
- Extract a usable prompt from the event data.
- Send the prompt to a KoboldCPP compatible API.
- Return the completion received from the LLM.

## Architecture

The system consists of several key components:

*   **`ai-ticket` Python Package**: The core logic, located in the `src/` directory. It includes modules for:
    *   `ai_ticket.find_name`: A utility function to extract a name (e.g., an AI agent's name) from a structured text block.
    *   `ai_ticket.events.inference`: Contains an `on_event` function for processing inference requests. This function extracts prompts and uses the `kobold_client`.
    *   `ai_ticket.backends.kobold_client`: Provides `get_kobold_completion` function to interact with a KoboldCPP API.
*   **Docker Service**: Defined in `docker-compose.yml`:
    *   `ai_ticket`: The main application service, built from the local Dockerfile. This service runs the Python application.
*   **GitHub Actions Workflows**: Located in `.github/workflows/`:
    *   `ci.yml`: Continuous Integration workflow that lints, tests, generates coverage reports, and builds the `ai_ticket` Docker image on pushes/PRs to `docker-main`.
    *   `docker-image.yml`: Builds and pushes the `ai_ticket` Docker image to Docker Hub on pushes to `docker-main`.
    *   `run.yml`: Manually triggered workflow to run the `ai_ticket` service using `docker-compose` (useful for running pre-built images).
    *   `static.yml`: Deploys static content (if any) to GitHub Pages from the `pyre` branch.
*   **Submodules**: The project uses Git submodules to include external repositories. While some, like `vendor/Auto-GPT` and `vendor/lollms`, were part of a previous architecture, they are not actively used by the current core application. The relevant ones for general utility or potential future integrations might include:
    *   `vendor/Auto-GPT-Benchmarks`
    *   `vendor/Auto-GPT-Plugin-Template`
    *   `vendor/lollms`
    *   `vendor/openai-python`
    It's important to note that `vendor/Auto-GPT` is included as a submodule but is not actively used by the current core application logic.

## Prerequisites

*   **Git**: For cloning the repository, including submodules.
*   **Python**: Version 3.10 (as specified in Dockerfile and CI).
*   **Docker**: For running the application via `docker-compose`.
*   **Docker Compose**: For orchestrating the `ai_ticket` container.
*   **KoboldCPP Instance**: A running instance of KoboldCPP (or a compatible API) accessible to the `ai_ticket` service.

## Getting Started

### 1. Clone the Repository

Clone the repository and initialize submodules:

```bash
git clone https://github.com/jmikedupont2/ai-ticket.git
cd ai-ticket
git submodule update --init --recursive
```

### 2. Configure KoboldCPP API Access

The `ai_ticket` service needs to connect to a KoboldCPP API. By default, it tries `http://localhost:5001/api`. You can configure this by setting the `KOBOLDCPP_API_URL` environment variable.
If running Docker on Docker Desktop, and your KoboldCPP instance is running on your host machine, you might use `http://host.docker.internal:5001/api`.

### 3. Local Development Setup (Optional, if not using Docker exclusively)

It's recommended to use a Python virtual environment for local development.

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
```

Install dependencies:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt # For linting and testing tools
```

The `ai_ticket` package itself can be installed in editable mode if you are developing it:
```bash
pip install -e .
```
Ensure your `KOBOLDCPP_API_URL` environment variable is set if you run the Python code directly.

## Running the Application

The primary way to run the system is using Docker Compose, which starts the `ai_ticket` service.

```bash
# Ensure KOBOLDCPP_API_URL is set in your environment if not using the default
# or if the default localhost:5001 is not accessible from within the container.
# For example, in your .env file (which is gitignored):
# KOBOLDCPP_API_URL=http://host.docker.internal:5001/api

docker-compose up
```

To run in detached mode:
```bash
docker-compose up -d
```

To see logs:
```bash
docker-compose logs -f ai_ticket
```

To stop the services:
```bash
docker-compose down
```


The `ai_ticket` service will process events sent to it (the mechanism for sending events, e.g. HTTP endpoint, would need to be defined or is part of how the Docker image's `ENTRYPOINT` or `CMD` is configured). It then queries the configured KoboldCPP backend.
=======
The system is designed to be extensible, and other services can be integrated as needed.

## Running Tests

Tests are written using `pytest`. Ensure you have installed development dependencies (`pip install -r requirements-dev.txt`).

To run all tests:

```bash
pytest tests/
```

## Linting and Formatting

This project uses `flake8` for linting, `black` for code formatting, and `isort` for import sorting. Configuration for these tools can be found in `setup.cfg` and `pyproject.toml`.

Ensure development dependencies are installed.

**Check for linting errors:**
```bash
flake8 .
```

**Check formatting (without making changes):**
```bash
black --check .
isort --check-only .
```

**Apply formatting:**
```bash
black .
isort .
```

These checks are also part of the Continuous Integration (CI) pipeline.

## Workflows

The project utilizes several GitHub Actions workflows:

*   **`ci.yml` (Continuous Integration)**:
    *   Triggered on pushes and pull requests to the `docker-main` branch.
    *   Performs:
        *   Dependency installation.
        *   Linting with `flake8`.
        *   Format checking with `black` and `isort`.
        *   Running tests with `pytest`.
        *   Building the `ai_ticket` Docker image to ensure it's valid.
*   **`docker-image.yml` (Docker Image Publishing)**:
    *   Triggered on pushes to the `docker-main` branch (typically after merging) and can be manually dispatched.
    *   Builds the `ai_ticket` Docker image and pushes it to Docker Hub, tagged with `latest` and the commit SHA.
*   **`run.yml` (Run System via Docker Compose)**:
    *   Manually triggered workflow (`workflow_dispatch`).
    *   Runs `docker-compose up --no-build` to start the `ai_ticket` service using pre-built images. This is useful for quick deployments or testing of the image defined in `docker-compose.yml`.
*   **`static.yml` (Static Pages Deployment)**:
    *   Triggered on pushes to the `pyre` branch or manually.
    *   Deploys content to GitHub Pages. The exact content being deployed would need to be in the `pyre` branch.

## Deployment

The `ai-ticket` application is deployed as a Docker image to Docker Hub. This is handled by the `docker-image.yml` workflow.

The image is tagged as:
*   `<your_dockerhub_username>/ai-ticket:latest`
*   `<your_dockerhub_username>/ai-ticket:sha-<commit_sha>`

(Note: Replace `<your_dockerhub_username>` with the actual Docker Hub username, e.g., `jmikedupont2` if that's where it's configured to go via secrets).
The service expects the `KOBOLDCPP_API_URL` environment variable to be set if the default is not suitable.

## Contributing

Contributions are welcome! Please follow these steps:

1.  Fork the repository.
2.  Create a new branch for your feature or bug fix (e.g., `git checkout -b feature/my-new-feature` or `bugfix/issue-123`).
3.  Make your changes.
4.  Ensure your code lints and formats correctly:
    ```bash
    flake8 .
    black .
    isort .
    ```
5.  Run tests and ensure they pass:
    ```bash
    pytest tests/
    ```
6.  Commit your changes with a clear and descriptive commit message.
7.  Push your branch to your fork.
8.  Create a Pull Request against the `docker-main` branch of the original repository.
9.  Ensure CI checks pass on your Pull Request.

## Examples

The primary interaction with `ai-ticket` is via its `on_event` function, which takes a dictionary containing event data. A typical piece of event data would include a "content" field with a prompt for an LLM.

Example of how `on_event` might be called (conceptually):
```python
from ai_ticket.events.inference import on_event

# Simulate an event payload
event_data = {
    "content": json.dumps({ # Content can be a JSON string
        "messages": [
            {"role": "user", "content": "Explain the theory of relativity in simple terms."}
        ],
        "model": "custom_model_if_needed_by_backend", # For Kobold, model is fixed in client
        "max_tokens": 100
    })
}
# Or simpler: event_data = {"content": "Explain the theory of relativity in simple terms."}

# This would trigger a call to the KoboldCPP backend
response = on_event(event_data)

if "completion" in response:
    print(f"LLM Response: {response['completion']}")
elif "error" in response:
    print(f"Error: {response['error']}")
```

The `find_name` utility can still be used independently:

```python
from ai_ticket import find_name

# Example string (details omitted for brevity, see tests/test_find_name.py)
long_json_like_string = """..."""
name = find_name(long_json_like_string)
print(f"Extracted Name: {name}") # Expected: Entrepreneur-GPT
```

## Troubleshooting

*   **Submodule Issues**: If you cloned without `--recursive` or submodules are out of sync, run `git submodule update --init --recursive`.
*   **Docker Build Failures**: Check logs for specific errors. Ensure Docker daemon is running and you have internet connectivity.
*   **Python Dependency Conflicts**: If using local development, ensure your virtual environment is activated and try reinstalling dependencies.
*   **KoboldCPP Connection Issues**:
    *   Ensure your KoboldCPP instance is running and accessible from where `ai_ticket` is running (either your host machine for local dev, or from within the Docker container).
    *   Verify the `KOBOLDCPP_API_URL` (default `http://localhost:5001/api` or environment variable) is correct.
    *   If running `ai_ticket` in Docker and KoboldCPP on the host, use `http://host.docker.internal:PORT/api` (Docker Desktop) or your host's IP address.
    *   Check KoboldCPP logs for any errors.

---
*This README was significantly expanded and restructured by an AI assistant.*
