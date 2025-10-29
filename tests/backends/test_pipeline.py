from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Iterable, Sequence

import pytest

from ai_ticket._compat import anyio
from ai_ticket.backends.base import (
    BackendError,
    BackendContext,
    CircuitBreakerConfig,
    CompletionRequest,
    CompletionResult,
    HedgedRequest,
    StreamEvent,
    StreamingNotSupported,
)
from ai_ticket.backends.pipeline import BackendPipeline, BackendSlotConfig


class _ScriptedBackend:
    """Test double for ``AsyncBackend`` with scripted responses."""

    def __init__(
        self,
        name: str,
        *,
        completions: Sequence[tuple[float, CompletionResult | Exception]] | None = None,
        streams: Sequence[Exception | Iterable[tuple[float, StreamEvent]]] | None = None,
    ) -> None:
        self.name = name
        self._completions = list(completions or [])
        self._streams = list(streams or [])
        self.acomplete_calls = 0
        self.astream_calls = 0

    async def acomplete(
        self,
        request: CompletionRequest,
        *,
        context: BackendContext | None = None,
    ) -> CompletionResult:
        del request, context
        try:
            delay, result = self._completions[self.acomplete_calls]
        except IndexError:  # pragma: no cover - guard rail for misconfigured tests
            raise AssertionError("Unexpected acomplete call") from None
        self.acomplete_calls += 1
        if delay:
            await anyio.sleep(delay)
        if isinstance(result, Exception):
            raise result
        return result

    async def astream(
        self,
        request: CompletionRequest,
        *,
        context: BackendContext | None = None,
    ) -> AsyncIterator[StreamEvent]:
        del request, context
        try:
            behavior = self._streams[self.astream_calls]
        except IndexError:  # pragma: no cover - guard rail for misconfigured tests
            raise AssertionError("Unexpected astream call") from None
        self.astream_calls += 1
        if isinstance(behavior, Exception):
            raise behavior

        for delay, chunk in behavior:
            if delay:
                await anyio.sleep(delay)
            yield chunk


async def _close_pipeline(pipeline: BackendPipeline) -> None:
    with contextlib.suppress(Exception):
        await pipeline.aclose()


def _pipeline(*slots: BackendSlotConfig) -> BackendPipeline:
    return BackendPipeline(list(slots))


def test_acomplete_returns_first_success() -> None:
    backend = _ScriptedBackend(
        "primary",
        completions=[(0.0, CompletionResult(completion="ok"))],
    )
    pipeline = _pipeline(BackendSlotConfig(backend=backend, concurrency=1))
    request = CompletionRequest(prompt="hi")

    async def _run() -> CompletionResult:
        try:
            return await pipeline.acomplete(request)
        finally:
            await _close_pipeline(pipeline)

    result = anyio.run(_run)

    assert result.is_success()
    assert result.completion == "ok"
    assert backend.acomplete_calls == 1


def test_acomplete_falls_back_after_failure() -> None:
    failing = _ScriptedBackend(
        "failing",
        completions=[(0.0, CompletionResult(error="boom", details="fail"))],
    )
    recovering = _ScriptedBackend(
        "recovering",
        completions=[(0.0, CompletionResult(completion="rescued"))],
    )
    pipeline = _pipeline(
        BackendSlotConfig(backend=failing, concurrency=1),
        BackendSlotConfig(backend=recovering, concurrency=1),
    )
    request = CompletionRequest(prompt="hi")

    async def _run() -> CompletionResult:
        try:
            return await pipeline.acomplete(request)
        finally:
            await _close_pipeline(pipeline)

    result = anyio.run(_run)

    assert result.is_success()
    assert result.completion == "rescued"
    assert failing.acomplete_calls == 1
    assert recovering.acomplete_calls == 1


def test_acomplete_skips_open_circuit() -> None:
    failing = _ScriptedBackend(
        "failing",
        completions=[
            (0.0, CompletionResult(error="boom")),
            (0.0, CompletionResult(error="boom")),
        ],
    )
    recovering = _ScriptedBackend(
        "recovering",
        completions=[
            (0.0, CompletionResult(completion="first")),
            (0.0, CompletionResult(completion="second")),
        ],
    )
    pipeline = _pipeline(
        BackendSlotConfig(
            backend=failing,
            concurrency=1,
            circuit_breaker=CircuitBreakerConfig(failure_threshold=1, reset_timeout=60.0),
        ),
        BackendSlotConfig(backend=recovering, concurrency=1),
    )
    request = CompletionRequest(prompt="hi")

    async def _run() -> tuple[CompletionResult, CompletionResult]:
        try:
            first = await pipeline.acomplete(request)
            second = await pipeline.acomplete(request)
            return first, second
        finally:
            await _close_pipeline(pipeline)

    first, second = anyio.run(_run)

    assert first.completion == "first"
    assert second.completion == "second"
    # Second request should not hit the failing backend because its circuit is open.
    assert failing.acomplete_calls == 1
    assert recovering.acomplete_calls == 2


def test_acomplete_hedging_returns_fastest_success() -> None:
    backend = _ScriptedBackend(
        "hedged",
        completions=[
            (0.03, CompletionResult(error="timeout")),
            (0.0, CompletionResult(completion="fast-success")),
        ],
    )
    pipeline = _pipeline(
        BackendSlotConfig(
            backend=backend,
            concurrency=1,
            hedging=HedgedRequest(hedges=1, hedge_delay=0.01),
        )
    )
    request = CompletionRequest(prompt="run")

    async def _run() -> CompletionResult:
        try:
            return await pipeline.acomplete(request)
        finally:
            await _close_pipeline(pipeline)

    result = anyio.run(_run)

    assert result.completion == "fast-success"
    # Both attempts should have executed due to hedging.
    assert backend.acomplete_calls == 2


def test_astream_yields_chunks() -> None:
    backend = _ScriptedBackend(
        "streamer",
        streams=[
            [
                (0.0, StreamEvent(delta="he")),
                (0.0, StreamEvent(delta="llo", done=True)),
            ]
        ],
    )
    pipeline = _pipeline(BackendSlotConfig(backend=backend, concurrency=1))
    request = CompletionRequest(prompt="hello", stream=True)

    async def _run() -> list[StreamEvent]:
        try:
            chunks = []
            async for chunk in pipeline.astream(request):
                chunks.append(chunk)
            return chunks
        finally:
            await _close_pipeline(pipeline)

    chunks = anyio.run(_run)

    assert [c.delta for c in chunks] == ["he", "llo"]
    assert chunks[-1].done is True
    assert backend.astream_calls == 1


def test_astream_raises_when_all_backends_fail() -> None:
    first = _ScriptedBackend(
        "first",
        streams=[StreamingNotSupported("no stream")],
    )
    second = _ScriptedBackend(
        "second",
        streams=[StreamingNotSupported("still no")],
    )
    pipeline = _pipeline(
        BackendSlotConfig(backend=first, concurrency=1),
        BackendSlotConfig(backend=second, concurrency=1),
    )
    request = CompletionRequest(prompt="hi", stream=True)

    async def _run() -> None:
        try:
            async for _ in pipeline.astream(request):
                pass
        finally:
            await _close_pipeline(pipeline)

    with pytest.raises(BackendError):
        anyio.run(_run)

    assert first.astream_calls == 1
    assert second.astream_calls == 1


def test_pipeline_respects_concurrency_limits() -> None:
    class _ConcurrentBackend:
        def __init__(self) -> None:
            self.name = "concurrent"
            self._lock = anyio.Lock()
            self._active = 0
            self.max_active = 0

        async def acomplete(
            self,
            request: CompletionRequest,
            *,
            context: BackendContext | None = None,
        ) -> CompletionResult:
            del request, context
            async with self._lock:
                self._active += 1
                self.max_active = max(self.max_active, self._active)
            try:
                await anyio.sleep(0.02)
                return CompletionResult(completion="ok")
            finally:
                async with self._lock:
                    self._active -= 1

    backend = _ConcurrentBackend()
    pipeline = BackendPipeline([
        BackendSlotConfig(backend=backend, concurrency=2),
    ])

    async def _runner() -> None:
        async def _invoke() -> None:
            result = await pipeline.acomplete(CompletionRequest(prompt="stress"))
            assert result.completion == "ok"

        try:
            async with anyio.create_task_group() as tg:
                for _ in range(6):
                    tg.start_soon(_invoke)
        finally:
            await pipeline.aclose()

    anyio.run(_runner)

    assert backend.max_active <= 2


def test_pipeline_hedging_cancels_slower_attempts() -> None:
    class _HedgedBackend:
        def __init__(self) -> None:
            self.name = "hedged"
            self.calls = 0
            self.cancelled = 0

        async def acomplete(
            self,
            request: CompletionRequest,
            *,
            context: BackendContext | None = None,
        ) -> CompletionResult:
            del request, context
            call_index = self.calls
            self.calls += 1
            if call_index == 0:
                try:
                    await anyio.sleep(0.2)
                except BaseException as exc:  # pragma: no cover - cancellation path
                    if isinstance(exc, anyio.get_cancelled_exc_class()):
                        self.cancelled += 1
                    raise
                return CompletionResult(error="slow")

            await anyio.sleep(0.01)
            return CompletionResult(completion="fast")

    backend = _HedgedBackend()
    pipeline = BackendPipeline([
        BackendSlotConfig(
            backend=backend,
            concurrency=2,
            hedging=HedgedRequest(hedges=1, hedge_delay=0.01),
        )
    ])

    async def _runner() -> CompletionResult:
        try:
            return await pipeline.acomplete(CompletionRequest(prompt="hedge"))
        finally:
            await pipeline.aclose()

    result = anyio.run(_runner)

    assert result.completion == "fast"
    assert backend.calls >= 2
    assert backend.cancelled >= 1
