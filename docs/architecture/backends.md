# Backend Orchestration Architecture

This document captures the architecture of the backend orchestration layer that
drives AI Ticket's completion requests. The refactor introduces a single
pipeline abstraction that can coordinate many backend implementations while
supporting hedged requests, connection pooling, and circuit breaking.

## Core Interfaces

All backends implement the `AsyncBackend` protocol defined in
`src/ai_ticket/backends/base.py`. The contract exposes three major concepts:

- `CompletionRequest` – a normalized payload describing the prompt, decoding
  controls, and optional metadata.
- `CompletionResult` – a structured response that carries either the generated
  text or a well-known error code with details.
- `astream` – an optional streaming iterator that yields `StreamEvent`
  instances; backends can raise `StreamingNotSupported` if they only provide
  full completions.

The module also defines reusable building blocks such as `HedgedRequest` and
`CircuitBreakerConfig` that feed into the orchestration layer.

## Backend Pipeline

`src/ai_ticket/backends/pipeline.py` contains the `BackendPipeline` class. A
pipeline is configured with one or more `BackendSlotConfig` instances. Each slot
declares:

- the backend implementation
- a concurrency limit (enforced via an `anyio.Semaphore`)
- hedging parameters (`hedges` + `hedge_delay`)
- circuit breaker thresholds
- optional `httpx.AsyncClient` keyword arguments (for example custom limits or
  timeouts)

The pipeline spins up an `httpx.AsyncClient` per slot configured with
connection pooling that matches the concurrency limit. This client is passed to
the backend via a `BackendContext`, enabling re-use of network connections
across hedged attempts.

### Hedged Scheduling

When `acomplete` is invoked the pipeline launches up to `hedges + 1` attempts in
parallel using an `anyio` task group. Subsequent attempts are staggered by the
configured `hedge_delay`. As soon as an attempt succeeds the pipeline cancels
the remaining tasks and returns the winning response. Failures are aggregated
and the final error is surfaced if all attempts fail.

### Circuit Breaking

Each slot maintains a simple counter-based circuit breaker. Consecutive failures
trip the breaker, and the backend is skipped until the configured
`reset_timeout` elapses. Successful completions reset the breaker immediately.

### Streaming

`BackendPipeline.astream` iterates through slots until it finds a backend that
supports streaming. If no backend succeeds the pipeline raises a `BackendError`
with the last recorded failure message.

## Default Configuration

The KoboldCPP backend (`KoboldBackend`) uses the pipeline internally via
`_build_default_pipeline`. The default configuration is intentionally minimal:

```python
BackendSlotConfig(
    backend=KoboldBackend(base_url=...),
    concurrency=5,
    hedging=HedgedRequest(hedges=0, hedge_delay=0.15),
)
```

Applications can construct their own pipelines with multiple slot configs to
blend providers (for example KoboldCPP + OpenAI) while tuning concurrency and
hedging parameters per backend.

## Configuration Surface

Key parameters can be overridden when instantiating `BackendSlotConfig`:

- `concurrency`: Number of simultaneous in-flight requests for the backend.
  This value also drives the `httpx` connection pool limits.
- `hedging.hedges`: Additional speculative requests started for the same
  prompt. Set to `0` to disable hedging.
- `hedging.hedge_delay`: Delay (in seconds) between launching hedged requests.
- `circuit_breaker.failure_threshold`: Number of consecutive failures required
  to open the breaker.
- `circuit_breaker.reset_timeout`: Cooldown period before requests are allowed
  again.
- `client_kwargs`: Passed through to `httpx.AsyncClient` allowing customization
  of TLS settings, proxies, or custom timeouts.

The asynchronous handlers in `src/ai_ticket/events/` continue to call
`async_get_kobold_completion`, but the refactor makes it straightforward to
inject a bespoke pipeline if future deployments need to orchestrate multiple
providers.

