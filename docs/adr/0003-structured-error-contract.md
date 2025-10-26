# ADR 0003: Enforce a Structured Error Response Contract

* **Status:** Accepted
* **Date:** 2024-05-20
* **Decision Makers:** Core maintainers
* **Tags:** error-handling, api, reliability

## Context

Consumers integrate AI Ticket into automation workflows and expect deterministic responses. Early prototypes returned raw
exception strings, which made client-side handling brittle and increased coupling to implementation details.

## Decision

1. Every failure path must surface an `{"error": "code", "details": "..."}` payload.
2. Error codes should be stable identifiers documented in code and README tables.
3. The Flask server is responsible for mapping error codes to HTTP status codes that align with REST semantics.

## Consequences

* Downstream services can build robust branching logic without parsing free-form messages.
* Facilitates observability by enabling structured logging and metrics keyed by error code.
* Introduces a maintenance requirement: new error codes must be added to the documentation and regression tests.
