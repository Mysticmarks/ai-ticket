"""Backend orchestration pipeline."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from ai_ticket._compat import anyio, httpx

from .base import (
    AsyncBackend,
    BackendContext,
    BackendError,
    CircuitBreakerConfig,
    CompletionRequest,
    CompletionResult,
    HedgedRequest,
    StreamEvent,
    StreamingNotSupported,
)


@dataclass
class CircuitBreaker:
    """Simple time-based circuit breaker implementation."""

    config: CircuitBreakerConfig
    failure_count: int = 0
    opened_at: float | None = None

    def allow_request(self) -> bool:
        if self.opened_at is None:
            return True
        elapsed = time.monotonic() - self.opened_at
        if elapsed >= self.config.reset_timeout:
            self.failure_count = 0
            self.opened_at = None
            return True
        return False

    def record_success(self) -> None:
        self.failure_count = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.config.failure_threshold:
            self.opened_at = time.monotonic()


@dataclass
class BackendSlotConfig:
    """Configuration for a backend within the pipeline."""

    backend: AsyncBackend
    concurrency: int = 5
    timeout: float | None = 120.0
    hedging: HedgedRequest = field(default_factory=HedgedRequest)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    client_kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class _BackendRuntime:
    config: BackendSlotConfig
    semaphore: anyio.Semaphore
    breaker: CircuitBreaker
    client: httpx.AsyncClient | None = None

    async def aclose(self) -> None:
        if self.client is not None:
            await self.client.aclose()


class BackendPipeline:
    """Coordinate requests across multiple backends with hedging."""

    def __init__(self, slots: Sequence[BackendSlotConfig]):
        self._runtimes: list[_BackendRuntime] = []
        for slot in slots:
            limits = slot.client_kwargs.get(
                "limits", httpx.Limits(max_connections=slot.concurrency, max_keepalive_connections=slot.concurrency)
            )
            timeout = slot.client_kwargs.get("timeout", slot.timeout)
            client = httpx.AsyncClient(limits=limits, timeout=timeout)
            runtime = _BackendRuntime(
                config=slot,
                semaphore=anyio.Semaphore(slot.concurrency),
                breaker=CircuitBreaker(slot.circuit_breaker),
                client=client,
            )
            self._runtimes.append(runtime)

    async def aclose(self) -> None:
        for runtime in self._runtimes:
            await runtime.aclose()

    async def acomplete(self, request: CompletionRequest) -> CompletionResult:
        last_error: CompletionResult | None = None

        for runtime in self._runtimes:
            if not runtime.breaker.allow_request():
                last_error = CompletionResult(
                    error="circuit_open",
                    details=f"Circuit breaker open for backend {runtime.config.backend.name}",
                )
                continue

            result = await self._execute_with_hedging(runtime, request)

            if result.is_success():
                runtime.breaker.record_success()
                return result

            runtime.breaker.record_failure()
            last_error = result

        return last_error or CompletionResult(
            error="no_backend_available",
            details="All configured backends are unavailable or failed.",
        )

    async def astream(self, request: CompletionRequest) -> AsyncIterator[StreamEvent]:
        last_error: CompletionResult | None = None

        for runtime in self._runtimes:
            if not runtime.breaker.allow_request():
                last_error = CompletionResult(
                    error="circuit_open",
                    details=f"Circuit breaker open for backend {runtime.config.backend.name}",
                )
                continue

            async with runtime.semaphore:
                context = BackendContext(client=runtime.client)
                try:
                    async for chunk in runtime.config.backend.astream(request, context=context):
                        yield chunk
                    runtime.breaker.record_success()
                    return
                except StreamingNotSupported:
                    runtime.breaker.record_failure()
                    last_error = CompletionResult(
                        error="streaming_not_supported",
                        details=f"Backend {runtime.config.backend.name} does not support streaming.",
                    )
                except Exception as exc:  # pragma: no cover - defensive safeguard
                    runtime.breaker.record_failure()
                    last_error = CompletionResult(
                        error="streaming_error",
                        details=f"Backend {runtime.config.backend.name} failed: {exc}",
                    )

        detail = last_error.details if last_error else "No streaming backends succeeded."
        raise BackendError(detail)

    async def _execute_with_hedging(
        self,
        runtime: _BackendRuntime,
        request: CompletionRequest,
    ) -> CompletionResult:
        hedging = runtime.config.hedging
        attempts = max(1, hedging.hedges + 1)

        results: list[CompletionResult] = []

        async def attempt(index: int) -> None:
            if index:
                await anyio.sleep(hedging.hedge_delay * index)
            async with runtime.semaphore:
                context = BackendContext(client=runtime.client)
                result = await runtime.config.backend.acomplete(request, context=context)
            results.append(result)
            if result.is_success():
                tg.cancel_scope.cancel()

        async with anyio.create_task_group() as tg:
            for idx in range(attempts):
                tg.start_soon(attempt, idx)

        for result in results:
            if result.is_success():
                return result

        return results[-1] if results else CompletionResult(
            error="backend_error",
            details=f"Backend {runtime.config.backend.name} produced no result.",
        )



__all__ = ["BackendPipeline", "BackendSlotConfig"]

