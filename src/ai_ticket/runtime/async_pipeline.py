"""Asynchronous orchestration utilities for inference workloads."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Mapping

from ai_ticket.events.async_inference import async_on_event
from ai_ticket.events.inference import InferenceResponse
from ai_ticket.telemetry import Status, StatusCode, get_meter, get_tracer


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

        self._tracer = get_tracer(f"{__name__}.{self.__class__.__name__}")
        self._meter = get_meter(f"{__name__}.{self.__class__.__name__}")
        self._handler_latency = self._meter.create_histogram(
            "ai_ticket_pipeline_handler_duration_seconds",
            unit="s",
            description="Duration of individual handler executions within the async pipeline.",
        )
        self._batch_latency = self._meter.create_histogram(
            "ai_ticket_pipeline_batch_duration_seconds",
            unit="s",
            description="Total time spent processing a pipeline batch.",
        )
        self._event_counter = self._meter.create_counter(
            "ai_ticket_pipeline_events_total",
            description="Number of events processed by the async pipeline.",
        )
        self._error_counter = self._meter.create_counter(
            "ai_ticket_pipeline_errors_total",
            description="Number of pipeline handler errors encountered.",
        )

    async def run_batch(self, events: Iterable[Mapping[str, object]]) -> list[InferenceResponse]:
        """Process ``events`` concurrently and return responses in order."""

        pipeline_attributes = {
            "pipeline": self.__class__.__name__,
            "max_concurrency": self._max_concurrency,
        }

        semaphore = asyncio.Semaphore(self._max_concurrency)
        tasks: list[asyncio.Task[tuple[int, InferenceResponse]]] = []

        async def _execute(index: int, event: Mapping[str, object]) -> tuple[int, InferenceResponse]:
            async with semaphore:
                start_time = time.perf_counter()
                attributes = {**pipeline_attributes, "stage": "run_batch", "event_index": index}
                with self._tracer.start_as_current_span("pipeline.run_batch.execute") as span:
                    span.set_attributes(attributes)
                    try:
                        result = await self._handler(event)
                        span.set_status(Status(StatusCode.OK))
                        return index, result
                    except Exception as exc:  # pragma: no cover - defensive telemetry hook
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        self._error_counter.add(1, attributes)
                        raise
                    finally:
                        duration = time.perf_counter() - start_time
                        self._handler_latency.record(duration, attributes)

        for index, event in enumerate(events):
            tasks.append(asyncio.create_task(_execute(index, event)))

        results: list[InferenceResponse | None] = [None] * len(tasks)

        start = time.perf_counter()
        try:
            for task in asyncio.as_completed(tasks):
                index, result = await task
                results[index] = result
                self._event_counter.add(1, {**pipeline_attributes, "stage": "run_batch"})
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        batch_duration = time.perf_counter() - start
        self._batch_latency.record(batch_duration, {**pipeline_attributes, "stage": "run_batch"})

        return [response for response in results if response is not None]

    async def iter_responses(
        self,
        events: Iterable[Mapping[str, object]],
    ) -> AsyncIterator[PipelineResult]:
        """Asynchronously yield ``PipelineResult`` objects as they complete."""

        queue: asyncio.Queue[PipelineResult | None] = asyncio.Queue()
        pipeline_attributes = {
            "pipeline": self.__class__.__name__,
            "max_concurrency": self._max_concurrency,
        }

        async def _produce() -> None:
            semaphore = asyncio.Semaphore(self._max_concurrency)

            async def _execute(event: Mapping[str, object]) -> None:
                async with semaphore:
                    start_time = time.perf_counter()
                    attributes = {**pipeline_attributes, "stage": "iter_responses"}
                    with self._tracer.start_as_current_span("pipeline.iter_responses.execute") as span:
                        span.set_attributes(attributes)
                        try:
                            response = await self._handler(event)
                            span.set_status(Status(StatusCode.OK))
                            await queue.put(PipelineResult(event=event, response=response))
                        except Exception as exc:  # pragma: no cover - defensive telemetry hook
                            span.record_exception(exc)
                            span.set_status(Status(StatusCode.ERROR, str(exc)))
                            self._error_counter.add(1, attributes)
                            raise
                        finally:
                            duration = time.perf_counter() - start_time
                            self._handler_latency.record(duration, attributes)

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

        start = time.perf_counter()
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                self._event_counter.add(1, {**pipeline_attributes, "stage": "iter_responses"})
                yield item
        finally:
            producer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await producer
            duration = time.perf_counter() - start
            self._batch_latency.record(duration, {**pipeline_attributes, "stage": "iter_responses"})


__all__ = ["AsyncInferencePipeline", "PipelineResult"]
