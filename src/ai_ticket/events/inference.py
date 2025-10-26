"""Inference event handler."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from ai_ticket.backends.kobold_client import KoboldCompletionResult, get_kobold_completion

from .prompt_extraction import PromptExtractionResult, extract_prompt
from .validation import ValidationError
from .common import validate_inference_event


@dataclass(frozen=True)
class CompletionResponse:
    """Successful inference outcome."""

    completion: str


@dataclass(frozen=True)
class ErrorResponse:
    """Error outcome suitable for HTTP responses."""

    error: str
    message: str
    status_code: int
    details: str | None = None


InferenceResponse = CompletionResponse | ErrorResponse


def on_event(event_data: Mapping[str, Any], *, logger: logging.Logger | None = None) -> InferenceResponse:
    """Handle inference events and return structured responses."""

    logger = logger or logging.getLogger(__name__)

    try:
        content_key = validate_inference_event(event_data)
        extraction: PromptExtractionResult = extract_prompt(event_data[content_key])
    except ValidationError as error:
        logger.warning("Inference event validation failed", extra={
            "error_code": error.code,
            "status_code": error.status_code,
            "details": error.details,
        })
        return ErrorResponse(
            error=error.code,
            message=error.message,
            status_code=error.status_code,
            details=error.details,
        )

    logger.info("Submitting prompt to completion backend", extra={"prompt_preview": extraction.prompt[:80]})
    backend_result = get_kobold_completion(prompt=extraction.prompt)

    if isinstance(backend_result, KoboldCompletionResult):
        if backend_result.completion:
            completion_text = backend_result.completion
            logger.info(
                "Completion backend succeeded",
                extra={"response_length": len(completion_text)},
            )
            return CompletionResponse(completion=completion_text)

        error_code = backend_result.error or "backend_error"
        error_detail = backend_result.details
    elif isinstance(backend_result, Mapping) and "completion" in backend_result:
        completion_text = str(backend_result["completion"])
        logger.info("Completion backend succeeded", extra={"response_length": len(completion_text)})
        return CompletionResponse(completion=completion_text)
    elif isinstance(backend_result, str):
        completion_text = backend_result
        logger.info("Completion backend succeeded", extra={"response_length": len(completion_text)})
        return CompletionResponse(completion=completion_text)
    else:
        error_code = "backend_error"
        error_detail = None

    logger.error("Completion backend failed", extra={
        "error_code": error_code,
        "details": error_detail,
    })
    return ErrorResponse(
        error=error_code,
        message="Failed to retrieve completion from backend.",
        status_code=502,
        details=error_detail,
    )


__all__ = ["on_event", "CompletionResponse", "ErrorResponse", "InferenceResponse"]
