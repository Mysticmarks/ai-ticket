from __future__ import annotations

import asyncio

import pytest

from ai_ticket.events.inference import CompletionResponse
from ai_ticket.runtime.async_pipeline import AsyncInferencePipeline, PipelineResult


def test_run_batch_preserves_order() -> None:
    async def handler(event: dict[str, str]) -> CompletionResponse:
        await asyncio.sleep(0)
        return CompletionResponse(completion=event["content"].upper())

    pipeline = AsyncInferencePipeline(handler=handler, max_concurrency=2)
    events = [{"content": "a"}, {"content": "b"}, {"content": "c"}]

    responses = asyncio.run(pipeline.run_batch(events))
    assert [response.completion for response in responses] == ["A", "B", "C"]


def test_run_batch_respects_concurrency() -> None:
    current = 0
    peak = 0
    lock = asyncio.Lock()

    async def handler(event: dict[str, str]) -> CompletionResponse:
        nonlocal current, peak
        async with lock:
            current += 1
            peak = max(peak, current)
        try:
            await asyncio.sleep(0.01)
        finally:
            async with lock:
                current -= 1
        return CompletionResponse(completion=event["content"])

    pipeline = AsyncInferencePipeline(handler=handler, max_concurrency=2)
    events = [{"content": str(i)} for i in range(5)]

    asyncio.run(pipeline.run_batch(events))
    assert peak <= 2


def test_iter_responses_streams_results() -> None:
    async def handler(event: dict[str, str]) -> CompletionResponse:
        await asyncio.sleep(0)
        return CompletionResponse(completion=event["content"].upper())

    pipeline = AsyncInferencePipeline(handler=handler, max_concurrency=2)
    events = [{"content": "x"}, {"content": "y"}]

    seen: list[PipelineResult] = []

    async def _collect() -> None:
        async for item in pipeline.iter_responses(events):
            seen.append(item)

    asyncio.run(_collect())

    assert {item.event["content"] for item in seen} == {"x", "y"}
    assert {item.response.completion for item in seen} == {"X", "Y"}


def test_pipeline_invalid_concurrency() -> None:
    with pytest.raises(ValueError):
        AsyncInferencePipeline(max_concurrency=0)
