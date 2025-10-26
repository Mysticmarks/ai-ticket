from __future__ import annotations

import asyncio

import pytest

from ai_ticket.backends.kobold_client import KoboldCompletionResult
from ai_ticket.events.async_inference import async_on_event
from ai_ticket.events.inference import CompletionResponse, ErrorResponse


def test_async_on_event_success(mocker: pytest.MockFixture) -> None:
    async def _fake_async_get(*args, **kwargs):
        return KoboldCompletionResult(completion="done")

    mocker.patch(
        "ai_ticket.events.async_inference.async_get_kobold_completion",
        side_effect=_fake_async_get,
    )

    result = asyncio.run(async_on_event({"content": "Hello"}))
    assert isinstance(result, CompletionResponse)
    assert result.completion == "done"


def test_async_on_event_validation_error(mocker: pytest.MockFixture) -> None:
    async def _fake_async_get(*args, **kwargs):
        return KoboldCompletionResult(completion="ignored")

    mocker.patch(
        "ai_ticket.events.async_inference.async_get_kobold_completion",
        side_effect=_fake_async_get,
    )

    result = asyncio.run(async_on_event({"other": "value"}))
    assert isinstance(result, ErrorResponse)
    assert result.error == "missing_content_field"
