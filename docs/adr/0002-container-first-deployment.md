# ADR 0002: Optimise for Container-First Delivery

* **Status:** Accepted
* **Date:** 2024-05-20
* **Decision Makers:** Core maintainers
* **Tags:** deployment, docker, devops

## Context

Users deploy AI Ticket to orchestrate LLM workloads in heterogeneous environments (self-hosted GPU nodes, managed clusters,
local developer machines). Providing consistent runtime behaviour across these targets was difficult when relying on bare-metal
Python execution.

## Decision

1. The Docker image built from the repository `Dockerfile` is the canonical distribution artifact.
2. `docker-compose.yml` and `docker-compose-run.yml` define the supported service graphs for local development and ad-hoc runs.
3. CI pipelines validate image buildability to catch dependency regressions early.

## Consequences

* Simplifies onboarding – developers can start the stack with one Compose command.
* Ensures environment parity between local development, CI, and production deployments.
* Requires careful handling of environment variables and secrets (documented in the README and contribution guidelines).
