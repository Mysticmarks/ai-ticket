from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from ai_ticket.events.inference import CompletionResponse
from ai_ticket.runtime.async_pipeline import AsyncInferencePipeline, PipelineResult

_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "events"


def _load_real_events(total: int = 60) -> list[dict[str, object]]:
    templates = json.loads((_DATA_DIR / "chat_messages.json").read_text())
    events: list[dict[str, object]] = []
    for index in range(total):
        template = templates[index % len(templates)]
        messages = [dict(message) for message in template["messages"]]
        for message in reversed(messages):
            if message.get("role") == "user":
                message["content"] = f"{message['content']} (request {index})"
                break
        payload = {"messages": messages}
        events.append({"content": json.dumps(payload)})
    return events


def _extract_prompt(event: dict[str, object]) -> str:
    payload = json.loads(str(event["content"]))
    return next(
        message["content"]
        for message in reversed(payload["messages"])
        if message.get("role") == "user"
    )


@pytest.fixture(scope="module")
def real_event_payloads() -> list[dict[str, object]]:
    return _load_real_events()


def test_run_batch_high_volume_concurrency(real_event_payloads: list[dict[str, object]]) -> None:
    current = 0
    peak = 0
    lock = asyncio.Lock()

    async def handler(event: dict[str, object]) -> CompletionResponse:
        nonlocal current, peak
        async with lock:
            current += 1
            peak = max(peak, current)
        try:
            await asyncio.sleep(0.002)
            prompt = _extract_prompt(event)
            return CompletionResponse(completion=prompt.upper())
        finally:
            async with lock:
                current -= 1

    pipeline = AsyncInferencePipeline(handler=handler, max_concurrency=6)

    responses = asyncio.run(pipeline.run_batch(real_event_payloads))

    expected = [_extract_prompt(event).upper() for event in real_event_payloads]
    assert [response.completion for response in responses] == expected
    assert peak <= 6
    assert peak > 1  # sanity check that concurrency actually occurred


def test_iter_responses_handles_backpressure(real_event_payloads: list[dict[str, object]]) -> None:
    seen: list[PipelineResult] = []

    async def handler(event: dict[str, object]) -> CompletionResponse:
        await asyncio.sleep(0.001)
        prompt = _extract_prompt(event)
        return CompletionResponse(completion=prompt.lower())

    pipeline = AsyncInferencePipeline(handler=handler, max_concurrency=5)

    async def _collect() -> None:
        async for result in pipeline.iter_responses(real_event_payloads):
            seen.append(result)
            if len(seen) % 10 == 0:
                await asyncio.sleep(0.0005)

    asyncio.run(_collect())

    expected = [_extract_prompt(event).lower() for event in real_event_payloads]
    assert sorted(result.response.completion for result in seen) == sorted(expected)
    original_contents = {event["content"] for event in real_event_payloads}
    assert {result.event["content"] for result in seen} == original_contents
    assert len(seen) == len(real_event_payloads)
