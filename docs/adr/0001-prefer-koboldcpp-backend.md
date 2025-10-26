# ADR 0001: Default to KoboldCPP-Compatible Backends

* **Status:** Accepted
* **Date:** 2024-05-20
* **Decision Makers:** Core maintainers
* **Tags:** backend, llm, integration

## Context

The service was originally conceived to proxy requests to a variety of experimental LLM backends. Experience showed that keeping
multiple unofficial clients in sync greatly increased maintenance cost, while the vast majority of real usage targeted
KoboldCPP-compatible endpoints.

## Decision

AI Ticket will optimise for KoboldCPP and other OpenAI-compatible chat endpoints. The inference layer will:

1. Expect the KoboldCPP API schema when interpreting responses.
2. Maintain best-effort compatibility with OpenAI-style chat completions for future extensibility.
3. Provide retry policies and fallback logic tailored to the KoboldCPP error surface (HTTP 429, transient 5xx, connection errors).

## Consequences

* Simplifies client code, test fixtures, and configuration.
* Enables deeper resilience tooling (e.g., structured error codes) for a single backend surface.
* Requires additional abstraction work before adding alternative providers; tracked on the project roadmap.
