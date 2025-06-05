# ai-ticket
[![CI Status](https://github.com/jmikedupont2/ai-ticket/actions/workflows/ci.yml/badge.svg)](https://github.com/jmikedupont2/ai-ticket/actions/workflows/ci.yml)

The AI Ticket system to handle the AI with tickets. Human Powered AI-Ops to Help you with the last mile of your AI code generated system.

* Join us on discord https://discord.com/invite/XWSam9kE

## Project Overview

ai-ticket is a Python-based system designed to facilitate interactions with AI models, particularly in the context of agent-based systems like Auto-GPT. It appears to use a ticket-based metaphor where user or system queries are handled as discrete units. The system leverages Docker for containerization and includes CI/CD workflows for testing, building, and deploying components.

The original summary described a user-driven ticket-based workflow:
- Users interact step-by-step, generating a "ticket" for each query/response.
- A proxy server facilitates these interactions.
- AutoGPT integrates via a "Request Assistance" action, linking to a GitHub ticket comment.
- AutoGPT waits for ticket updates with user-generated responses to continue its workflow.

## Architecture

The system consists of several key components:

*   **`ai-ticket` Python Package**: The core logic, located in the `src/` directory. It includes modules for:
    *   `ai_ticket.find_name`: A function to extract a name (e.g., an AI agent's name) from a structured text block.
    *   `ai_ticket.events.inference`: Contains an `on_event` function, likely used for processing inference requests or events from an AI system.
*   **Docker Services**: Defined in `docker-compose.yml`:
    *   `ai_ticket`: The main application service, built from the local Dockerfile.
    *   `autogpt`: A service running an instance of Auto-GPT, which appears to be integrated with `ai_ticket`. It installs `ai_ticket` as a plugin.
    *   `mockopenai`: A service based on `lollms`, likely providing a mock or alternative OpenAI-compatible API endpoint for development or testing.
*   **GitHub Actions Workflows**: Located in `.github/workflows/`:
    *   `ci.yml`: Continuous Integration workflow that lints, tests, and builds the `ai_ticket` Docker image on pushes/PRs to `docker-main`.
    *   `docker-image.yml`: Builds and pushes the `ai_ticket` Docker image to Docker Hub on pushes to `docker-main`.
    *   `run.yml`: Manually triggered workflow to run the full `docker-compose` setup.
    *   `static.yml`: Deploys static content (if any) to GitHub Pages from the `pyre` branch.
*   **Submodules**: The project uses Git submodules to include external repositories:
    *   `vendor/Auto-GPT`
    *   `vendor/Auto-GPT-Benchmarks`
    *   `vendor/Auto-GPT-Plugin-Template`
    *   `vendor/lollms`
    *   `vendor/openai-python`

## Prerequisites

*   **Git**: For cloning the repository, including submodules.
*   **Python**: Version 3.10 (as specified in Dockerfile and CI).
*   **Docker**: For running the application via `docker-compose`.
*   **Docker Compose**: For orchestrating the multi-container setup.

## Getting Started

### 1. Clone the Repository

Clone the repository and initialize submodules:

```bash
git clone https://github.com/jmikedupont2/ai-ticket.git
cd ai-ticket
git submodule update --init --recursive
```

### 2. Local Development Setup (Optional, if not using Docker exclusively)

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

## Running the Application

The primary way to run the system is using Docker Compose, which orchestrates the `ai_ticket`, `autogpt`, and `mockopenai` services.

```bash
docker-compose up
```

To run in detached mode:
```bash
docker-compose up -d
```

To see logs:
```bash
docker-compose logs -f
```

To stop the services:
```bash
docker-compose down
```

The `autogpt` service is configured to run with specific goals related to introspection. The `mockopenai` service exposes a port (5000) which might be used by Auto-GPT.

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
*   **`run.yml` (Run Full System)**:
    *   Manually triggered workflow (`workflow_dispatch`).
    *   Runs `docker-compose up --no-build` to start the full application stack using pre-built images.
*   **`static.yml` (Static Pages Deployment)**:
    *   Triggered on pushes to the `pyre` branch or manually.
    *   Deploys content to GitHub Pages. The exact content being deployed would need to be in the `pyre` branch.

## Deployment

The `ai-ticket` application is deployed as a Docker image to Docker Hub. This is handled by the `docker-image.yml` workflow.

The image is tagged as:
*   `<your_dockerhub_username>/ai-ticket:latest`
*   `<your_dockerhub_username>/ai-ticket:sha-<commit_sha>`

(Note: Replace `<your_dockerhub_username>` with the actual Docker Hub username, e.g., `jmikedupont2` if that's where it's configured to go via secrets).

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

(This section can be expanded with specific examples of how `ai-ticket` is used, perhaps showing input/output of the `find_name` function or how the `on_event` is triggered and what it does.)

Example of `find_name` usage (from tests):
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
*   **`mockopenai` service**: If Auto-GPT cannot connect to an OpenAI-compatible endpoint, ensure the `mockopenai` service is running correctly and configured as the endpoint for Auto-GPT if it's being used.

---
*This README was significantly expanded and restructured by an AI assistant.*
