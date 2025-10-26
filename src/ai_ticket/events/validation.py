"""Validation primitives shared by event handlers.

This module centralises the validation errors that can occur when handling
inference events.  Each error carries both a machine-friendly ``code`` and an
HTTP status code so that API layers can translate validation failures into
consistent HTTP responses without bespoke mapping logic.

The currently defined validation errors are:

``invalid_input_format`` (400)
    Raised when the event payload is not a mapping.

``missing_content_field`` (400)
    Raised when the ``content`` field is absent from the event payload.

``prompt_extraction_failed`` (422)
    Raised when the payload could not be translated into a usable prompt.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationError(Exception):
    """Exception representing a validation failure with HTTP context.

    Parameters
    ----------
    code:
        Machine readable identifier for the error condition.  These values are
        stable so they can be used for telemetry or localisation.
    message:
        Human readable summary that can be surfaced in API responses.
    status_code:
        HTTP status code that most closely aligns with the validation failure.
    details:
        Optional free-form diagnostic information.
    """

    code: str
    message: str
    status_code: int
    details: str | None = None

    def __str__(self) -> str:  # pragma: no cover - trivial override
        if self.details:
            return f"{self.message} ({self.details})"
        return self.message


__all__ = ["ValidationError"]
