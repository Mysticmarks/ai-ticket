"""Core backend interfaces and request/response models.

This module defines the contracts that all backend implementations must
implement in order to integrate with the orchestration pipeline. The
interfaces deliberately focus on asynchronous interactions because the
pipeline coordinates concurrency, hedging and streaming behaviour using
``anyio`` task groups.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class CompletionRequest:
    """Normalized request payload supplied to completion backends."""

    prompt: str
    max_tokens: int = 256
    temperature: float = 0.7
    top_p: float = 1.0
    stream: bool = False
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class CompletionResult:
    """Generic backend completion result."""

    completion: str | None = None
    error: str | None = None
    details: str | None = None
    raw_response: Any | None = None

    def is_success(self) -> bool:
        return self.completion is not None


@dataclass(frozen=True)
class StreamEvent:
    """Represents a chunk emitted by a streaming backend."""

    delta: str
    done: bool = False
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class HedgedRequest:
    """Configuration for hedged backend calls."""

    hedges: int = 0
    hedge_delay: float = 0.15


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Configuration describing circuit breaker behaviour."""

    failure_threshold: int = 5
    reset_timeout: float = 30.0


@dataclass
class BackendContext:
    """Runtime context passed to backends for re-usable clients."""

    client: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class AsyncBackend(Protocol):
    """Protocol that all backend implementations must satisfy."""

    name: str

    async def acomplete(
        self,
        request: CompletionRequest,
        *,
        context: BackendContext | None = None,
    ) -> CompletionResult:
        """Return a full completion for ``request``."""

    async def astream(
        self,
        request: CompletionRequest,
        *,
        context: BackendContext | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Yield completion deltas for ``request`` in streaming mode."""


class StreamingNotSupported(RuntimeError):
    """Raised when streaming is requested but not supported by a backend."""


class BackendError(Exception):
    """Base exception for backend orchestration errors."""


class HedgingStrategy(abc.ABC):
    """Strategy object responsible for hedged scheduling."""

    @abc.abstractmethod
    async def run(
        self,
        backend: AsyncBackend,
        request: CompletionRequest,
        context: BackendContext | None,
    ) -> CompletionResult:
        """Execute a hedged request and return the best result."""

