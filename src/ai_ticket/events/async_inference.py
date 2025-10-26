"""Asynchronous inference event handler."""

from __future__ import annotations

import logging
from typing import Any, Mapping

from ai_ticket.backends.kobold_client import (
    KoboldCompletionResult,
    async_get_kobold_completion,
)

from .common import validate_inference_event
from .inference import CompletionResponse, ErrorResponse, InferenceResponse
from .prompt_extraction import PromptExtractionResult, extract_prompt
from .validation import ValidationError


async def async_on_event(
    event_data: Mapping[str, Any],
    *,
    logger: logging.Logger | None = None,
) -> InferenceResponse:
    """Asynchronously handle inference events using the async backend client."""

    logger = logger or logging.getLogger(__name__)

    try:
        content_key = validate_inference_event(event_data)
        extraction: PromptExtractionResult = extract_prompt(event_data[content_key])
    except ValidationError as error:
        logger.warning(
            "Async inference event validation failed",
            extra={
                "error_code": error.code,
                "status_code": error.status_code,
                "details": error.details,
            },
        )
        return ErrorResponse(
            error=error.code,
            message=error.message,
            status_code=error.status_code,
            details=error.details,
        )

    logger.info(
        "Submitting prompt to async completion backend",
        extra={"prompt_preview": extraction.prompt[:80]},
    )
    backend_result = await async_get_kobold_completion(prompt=extraction.prompt)

    if isinstance(backend_result, KoboldCompletionResult) and backend_result.completion:
        completion_text = backend_result.completion
        logger.info(
            "Async completion backend succeeded",
            extra={"response_length": len(completion_text)},
        )
        return CompletionResponse(completion=completion_text)

    if isinstance(backend_result, Mapping) and "completion" in backend_result:
        completion_text = str(backend_result["completion"])
        logger.info(
            "Async completion backend succeeded",
            extra={"response_length": len(completion_text)},
        )
        return CompletionResponse(completion=completion_text)

    if isinstance(backend_result, str):
        completion_text = backend_result
        logger.info(
            "Async completion backend succeeded",
            extra={"response_length": len(completion_text)},
        )
        return CompletionResponse(completion=completion_text)

    if isinstance(backend_result, KoboldCompletionResult):
        error_code = backend_result.error or "backend_error"
        error_detail = backend_result.details
    else:
        error_code = "backend_error"
        error_detail = None

    logger.error(
        "Async completion backend failed",
        extra={"error_code": error_code, "details": error_detail},
    )
    return ErrorResponse(
        error=error_code,
        message="Failed to retrieve completion from backend.",
        status_code=502,
        details=error_detail,
    )


__all__ = ["async_on_event"]
