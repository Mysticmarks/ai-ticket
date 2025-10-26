"""Shared helpers for inference event handlers."""

from __future__ import annotations

from typing import Any, Mapping

from .validation import ValidationError


CONTENT_FIELD = "content"


def validate_inference_event(event_data: Mapping[str, Any]) -> str:
    """Validate the structure of an inference event payload.

    Parameters
    ----------
    event_data:
        Raw payload supplied to the event handler.

    Returns
    -------
    str
        The key containing the prompt content within ``event_data``.

    Raises
    ------
    ValidationError
        If the payload is not a mapping or lacks the content field.
    """

    if not isinstance(event_data, Mapping):
        raise ValidationError(
            code="invalid_input_format",
            message="Event data must be a mapping.",
            status_code=400,
        )
    if CONTENT_FIELD not in event_data:
        raise ValidationError(
            code="missing_content_field",
            message="The 'content' field is required.",
            status_code=400,
        )
    return CONTENT_FIELD


__all__ = ["validate_inference_event", "CONTENT_FIELD"]
