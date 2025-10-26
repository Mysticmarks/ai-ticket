# ai-ticket
[![CI Status](https://github.com/jmikedupont2/ai-ticket/actions/workflows/ci.yml/badge.svg)](https://github.com/jmikedupont2/ai-ticket/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jmikedupont2/ai-ticket/branch/docker-main/graph/badge.svg)](https://codecov.io/gh/jmikedupont2/ai-ticket)
[![Linting: Flake8](https://img.shields.io/badge/linting-flake8-blue.svg)](https://flake8.pycqa.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Imports: isort](https://img.shields.io/badge/%20imports-isort-%231674b1?style=flat&labelColor=ef8336)](https://pycqa.github.io/isort/)

The **AI Ticket** service streamlines event-driven interactions with Large Language Models (LLMs) – optimised for KoboldCPP –
by normalising inbound payloads, orchestrating resilient inference calls, and returning structured responses suitable for
automation pipelines.

> 💬 Join the discussion on Discord: https://discord.com/invite/XWSam9kE (invite may change)

## Feature highlights

* **Event-driven orchestration** – `ai_ticket.events.inference.on_event` validates incoming payloads, extracts prompts from raw
  strings or OpenAI-style message lists, and encapsulates the response contract shared by the HTTP API and the Python package.
* **Resilient KoboldCPP integration** – `ai_ticket.backends.kobold_client.get_kobold_completion` performs endpoint
  prioritisation, exponential backoff, and structured error classification for transient and terminal failures.
* **Container-first delivery** – the project ships with a production-ready `Dockerfile`, Compose descriptors, and a Gunicorn
  entrypoint for reliable deployment.
* **Observability via structured logging** – the Flask server and inference pipeline emit log records with consistent
  formatting and log levels that can be tuned through environment variables.
* **Tests and CI/CD guard-rails** – pytest suites, static analysis, and Docker build validation run through GitHub Actions to
  catch regressions early.

## Architecture at a glance

```
┌────────────┐    JSON       ┌─────────────────────┐      ┌────────────────────┐
│ HTTP client├──────────────▶│Flask server (/event)├──────▶│on_event dispatcher │
└────────────┘               └─────────────────────┘      └────────────────────┘
                                                                  │
                                                                  ▼
                                                         ┌────────────────────┐
                                                         │Kobold client       │
                                                         │(fallback + retries)│
                                                         └────────────────────┘
                                                                  │
                                                                  ▼
                                                         ┌────────────────────┐
                                                         │Structured response │
                                                         └────────────────────┘
```

* **HTTP surface** – `src/ai_ticket/server.py` hosts Flask endpoints (`/event`, `/health`) and applies request logging plus
  status-code mapping for common failure scenarios.
* **Inference workflow** – `src/ai_ticket/events/inference.py` is the single entry point for all inference requests and can be
  imported directly for serverless or batch execution contexts.
* **Backend integration** – `src/ai_ticket/backends/kobold_client.py` encapsulates session management and response parsing for
  KoboldCPP-compatible APIs.

Additional design rationale is captured in [Architecture Decision Records](docs/adr/README.md).

## Deployment

### 1. Configure environment

Create a `.env` file in the repository root (or set variables directly in your shell/CI):

```env
KOBOLDCPP_API_URL=http://host.docker.internal:5001/api
LOG_LEVEL=INFO
PORT=5000
```

### 2. Run with Docker Compose (recommended)

```bash
docker-compose up --build
```

* The API becomes available at `http://localhost:${PORT:-5000}/event`.
* Health probes use `http://localhost:${PORT:-5000}/health`.
* Use `docker-compose down` to stop services and `docker-compose logs -f ai_ticket` to inspect runtime behaviour.

### 3. Local development without containers

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -e .
export KOBOLDCPP_API_URL=http://localhost:5001/api
flask --app ai_ticket.server run --host 0.0.0.0 --port 5000
```

## Configuration quick reference

| Variable            | Default                     | Description                                                  |
|---------------------|-----------------------------|--------------------------------------------------------------|
| `KOBOLDCPP_API_URL` | `http://localhost:5001/api` | Target KoboldCPP-compatible inference endpoint.              |
| `LOG_LEVEL`         | `INFO`                      | Python logging level (`DEBUG`, `INFO`, `WARNING`, ...).      |
| `PORT`              | `5000`                      | Port used by the Flask development server (not Gunicorn).    |

## Roadmap

The near-term focus areas are documented to help contributors align on priorities:

* **UI/UX extension** – design and implement a thin management console for prompt history and system health (see
  [UI/UX notes](docs/ui-ux-roadmap.md)).
* **Backend pluggability** – introduce a provider interface to support multiple LLM backends alongside KoboldCPP.
* **Observability** – add structured metrics export (e.g., Prometheus) and trace correlation IDs for multi-service chains.
* **Load & soak testing** – automate performance regression tests for key workloads to validate retry budgets and error paths.

## Repository hygiene

* The historical Git submodules have been permanently removed. The repository intentionally **does not contain a `.gitmodules`
  file**, and the `vendor/` directory has been deleted to avoid stale dependencies.
* If you are upgrading an older checkout, prune any lingering `vendor/*` folders in your workspace to stay aligned with the
  tracked tree.

## Documentation index

* [Architecture Decision Records](docs/adr/README.md)
* [UI/UX strategy and keyboard shortcuts](docs/ui-ux-roadmap.md)
* [Contribution guidelines](CONTRIBUTING.md)

## Contributing

We welcome issues and pull requests! Before starting significant work, please review the
[contribution guidelines](CONTRIBUTING.md) which cover style conventions, threading/async considerations, and logging practices.

---

*This README reflects the state of the `work` branch after the repository cleanup and documentation refresh.*
