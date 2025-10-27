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
* **Asynchronous orchestration** – `ai_ticket.backends.kobold_client.async_get_kobold_completion` and the
  `AsyncInferencePipeline` enable concurrent inference with cooperative cancellation and ordered response delivery.
* **Container-first delivery** – the project ships with a production-ready `Dockerfile`, Compose descriptors, and a Gunicorn
  entrypoint for reliable deployment.
* **Operator-focused CLI** – the bundled `ai-ticket` command provides accent-themed terminal controls for starting the
  server, issuing prompts, and running health diagnostics with structured feedback.
* **Observability via structured logging & metrics** – the Flask server emits JSON logs and exposes Prometheus-compatible
  counters, gauges, and histograms for health, error rates, and latency.
* **Authentication & request throttling** – bearer-token authentication and per-client request quotas protect the `/event`
  endpoint from abuse out-of-the-box.
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

* **HTTP surface** – `src/ai_ticket/server.py` hosts Flask endpoints (`/event`, `/health`, `/metrics`) with authentication,
  rate limiting, structured logging, and status-code mapping for common failure scenarios.
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
RATE_LIMIT_REQUESTS=120
RATE_LIMIT_WINDOW_SECONDS=60
METRICS_NAMESPACE=ai_ticket
TRUST_PROXY_COUNT=0
# Provide at least one token when enabling auth without Docker secrets
# AI_TICKET_AUTH_TOKEN=local-dev-token
```

### 2. Run with Docker Compose (recommended)

```bash
docker compose up --build
```

Before launching, copy `ops/secrets/ai_ticket_auth_token.txt.example` to `ops/secrets/ai_ticket_auth_token.txt` and replace the
placeholder with strong bearer tokens. Place TLS materials in `ops/certs/server.crt` and `ops/certs/server.key` (self-signed
certificates work for local development).

* The API becomes available at `https://localhost:${TLS_PORT:-8443}/event` via the TLS offload proxy. You can still reach the
  Flask container directly on `http://localhost:${PORT:-5000}/event` when running outside of Docker.
* Health probes use `https://localhost:${TLS_PORT:-8443}/health`.
* Prometheus scrapers can collect metrics from `https://localhost:${TLS_PORT:-8443}/metrics`.
* Use `docker compose down` to stop services and `docker compose logs -f ai_ticket` to inspect runtime behaviour.

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

### Authentication & throttling

The `/event` endpoint requires authentication when either `AI_TICKET_AUTH_TOKEN` (comma-separated tokens) or
`AI_TICKET_AUTH_TOKEN_FILE` (newline-delimited tokens) is configured. Clients must include one of the following headers:

* `Authorization: Bearer <token>`
* `X-API-Key: <token>`

Requests are throttled per client IP using the `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW_SECONDS` settings. The application
trusts proxy headers when `TRUST_PROXY_COUNT` is greater than zero, enabling accurate rate limits behind the bundled TLS proxy.

Prometheus metrics are available at `/metrics` and include latency, error, and in-flight request tracking. Adjust
`METRICS_NAMESPACE` to namescope the exported series for your monitoring stack.

### 4. Command-line interface

The package installs an `ai-ticket` executable that wraps common operational tasks with an accent-tinted terminal interface.

```bash
# Submit a prompt to a running server
ai-ticket prompt "Summarise open tickets" --server-url http://localhost:5000

# Perform a health check with a custom accent colour
ai-ticket health --accent violet --server-url http://localhost:5000

# Launch the production server (Gunicorn with threaded workers by default)
ai-ticket serve --workers 4 --threads 8

# Launch the development server with Flask's auto-reloader
ai-ticket serve --reload
```

Use `ai-ticket --help` or `ai-ticket <command> --help` to explore additional options such as sampling parameters,
worker classes, and theming controls.

## Configuration quick reference

| Variable                       | Default                     | Description                                                                 |
|--------------------------------|-----------------------------|-----------------------------------------------------------------------------|
| `KOBOLDCPP_API_URL`            | `http://localhost:5001/api` | Target KoboldCPP-compatible inference endpoint.                             |
| `LOG_LEVEL`                    | `INFO`                      | Python logging level (`DEBUG`, `INFO`, `WARNING`, ...).                     |
| `PORT`                         | `5000`                      | Default port used by the CLI and Flask development server.                   |
| `AI_TICKET_AUTH_TOKEN`         | _unset_                     | Comma-separated bearer tokens accepted by the `/event` endpoint.           |
| `AI_TICKET_AUTH_TOKEN_FILE`    | _unset_                     | Path to newline-delimited bearer tokens (set automatically via Docker secret). |
| `RATE_LIMIT_REQUESTS`          | `120`                       | Requests allowed per client within a window.                                |
| `RATE_LIMIT_WINDOW_SECONDS`    | `60`                        | Duration of the rate limit window (seconds).                                |
| `METRICS_NAMESPACE`            | `ai_ticket`                 | Prometheus namespace prefix for exported metrics.                           |
| `TRUST_PROXY_COUNT`            | `0`                         | Number of reverse proxies to trust when deriving client IP addresses.       |
| `TLS_PORT`                     | `8443`                      | External TLS port exposed by the Compose TLS proxy.                         |
| `WERKZEUG_LOG_LEVEL`           | matches `LOG_LEVEL`         | Optional override for Werkzeug's access log level.                          |

## Roadmap

The near-term focus areas are documented to help contributors align on priorities:

* **Dashboard deepening** – extend the shipped SPA with prompt history, keyboard shortcut overlays, and admin controls (see
  [UI/UX notes](docs/ui-ux-roadmap.md)).
* **Backend pluggability** – introduce a provider interface to support multiple LLM backends alongside KoboldCPP.
* **Shared state services** – move authentication, rate limiting, and metrics aggregation to persistent stores to enable
  horizontal scaling.
* **Load & soak testing** – automate performance regression tests for key workloads to validate retry budgets and error paths.
* **Release automation** – codify a packaging and changelog pipeline so operators can track and deploy tagged builds reliably.

## Repository hygiene

* The historical Git submodules have been permanently removed. The repository intentionally **does not contain a `.gitmodules`
  file**, and the `vendor/` directory has been deleted to avoid stale dependencies.
* If you are upgrading an older checkout, prune any lingering `vendor/*` folders in your workspace to stay aligned with the
  tracked tree.

## Documentation index

* [Architecture Decision Records](docs/adr/README.md)
* [UI/UX strategy and keyboard shortcuts](docs/ui-ux-roadmap.md)
* [Asynchronous pipeline usage](docs/async_pipeline.md)
* [Contribution guidelines](CONTRIBUTING.md)

## Contributing

We welcome issues and pull requests! Before starting significant work, please review the
[contribution guidelines](CONTRIBUTING.md) which cover style conventions, threading/async considerations, and logging practices.

---

*This README reflects the state of the `work` branch after the repository cleanup and documentation refresh.*
