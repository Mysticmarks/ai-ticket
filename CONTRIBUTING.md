# Contributing to AI Ticket

Thank you for investing time in improving AI Ticket! This guide summarises expectations for pull requests and issue triage.

## Getting started

1. Fork the repository and create a topic branch from `work` (or the target release branch).
2. Install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt -r requirements-dev.txt
   pip install -e .
   ```
3. Configure required environment variables (see the README for a quick reference) before running tests or the Flask server.

## Code style and linting

* **Formatting** – run `black .` to auto-format Python files. The CI pipeline enforces Black with default settings.
* **Imports** – run `isort .` to group and order imports according to the "black" profile.
* **Static analysis** – run `flake8` and resolve reported warnings before submitting a PR.
* **Type hints** – add or preserve type annotations when touching inference and backend modules to improve readability.
* **Tests** – execute `pytest` and ensure new behaviour has unit tests where feasible.

### Threading and concurrency model

* Production deployments rely on **Gunicorn** worker processes managing the Flask app. Avoid storing mutable global state in
  module-level variables; prefer request-scoped data or dependency injection.
* The inference layer should remain synchronous until a concrete async backend is introduced. When adding asynchronous code,
  wrap it carefully so that Gunicorn workers continue to function without event-loop conflicts.
* When performing network retries, prefer the existing backoff utilities in `ai_ticket.backends.kobold_client` to guarantee
  consistent behaviour across threads/processes.

### Logging conventions

* Use the standard library `logging` module with module-level loggers (`logger = logging.getLogger(__name__)`).
* Honour the `LOG_LEVEL` environment variable; do not override global logging configuration inside libraries.
* Log structured dictionaries or key-value strings where possible (`extra={"event_id": ..., "error": ...}`) to aid future log
  aggregation.
* Do not log secrets, API keys, or full prompt payloads that may contain sensitive information.

## Commit hygiene

* Write descriptive commit messages in the imperative mood (e.g., "Add retry budget metrics").
* Keep pull requests focused; unrelated refactors should be submitted separately.
* Update documentation (README, ADRs, UI/UX notes) when introducing or changing observable behaviour.

## Pull request checklist

Before requesting a review, confirm the following:

- [ ] Tests pass locally (`pytest`).
- [ ] Linting and formatting checks pass (`black`, `isort`, `flake8`).
- [ ] Relevant documentation was updated.
- [ ] Significant changes were discussed in an ADR or existing ADR was amended.

We appreciate your contributions and look forward to collaborating!
