"""Asynchronous orchestration utilities for inference workloads."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Mapping

from ai_ticket.events.async_inference import async_on_event
from ai_ticket.events.inference import InferenceResponse


@dataclass(frozen=True)
class PipelineResult:
    """Container binding an event payload to its inference response."""

    event: Mapping[str, object]
    response: InferenceResponse


class AsyncInferencePipeline:
    """High-level helper that parallelises inference across many events.

    The pipeline coordinates an ``async_on_event``-compatible handler using a
    semaphore to cap concurrency.  Results are yielded in the same order as the
    incoming events even though execution is parallelised.
    """

    def __init__(
        self,
        handler: Callable[[Mapping[str, object]], Awaitable[InferenceResponse]] = async_on_event,
        *,
        max_concurrency: int = 8,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self._handler = handler
        self._max_concurrency = max_concurrency

    async def run_batch(self, events: Iterable[Mapping[str, object]]) -> list[InferenceResponse]:
        """Process ``events`` concurrently and return responses in order."""

        semaphore = asyncio.Semaphore(self._max_concurrency)
        tasks: list[asyncio.Task[tuple[int, InferenceResponse]]] = []

        async def _execute(index: int, event: Mapping[str, object]) -> tuple[int, InferenceResponse]:
            async with semaphore:
                result = await self._handler(event)
                return index, result

        for index, event in enumerate(events):
            tasks.append(asyncio.create_task(_execute(index, event)))

        results: list[InferenceResponse | None] = [None] * len(tasks)

        try:
            for task in asyncio.as_completed(tasks):
                index, result = await task
                results[index] = result
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        return [response for response in results if response is not None]

    async def iter_responses(
        self,
        events: Iterable[Mapping[str, object]],
    ) -> AsyncIterator[PipelineResult]:
        """Asynchronously yield ``PipelineResult`` objects as they complete."""

        queue: asyncio.Queue[PipelineResult | None] = asyncio.Queue()

        async def _produce() -> None:
            semaphore = asyncio.Semaphore(self._max_concurrency)

            async def _execute(event: Mapping[str, object]) -> None:
                async with semaphore:
                    response = await self._handler(event)
                    await queue.put(PipelineResult(event=event, response=response))

            producers = [asyncio.create_task(_execute(event)) for event in events]
            try:
                await asyncio.gather(*producers)
            finally:
                for task in producers:
                    if not task.done():
                        task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
                await queue.put(None)

        producer = asyncio.create_task(_produce())

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            producer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await producer


__all__ = ["AsyncInferencePipeline", "PipelineResult"]
