"""Utilities for extracting prompts from heterogeneous payloads."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .validation import ValidationError


@dataclass(frozen=True)
class PromptExtractionResult:
    """Structured outcome of a prompt extraction operation."""

    prompt: str


USER_ROLE = "user"


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _iter_user_messages(messages: Sequence[Mapping[str, Any]]) -> Iterable[str]:
    for message in messages:
        if not _is_mapping(message):
            continue
        if message.get("role") == USER_ROLE:
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                yield content


def _prompt_from_mapping(data: Mapping[str, Any]) -> str | None:
    if "messages" in data and isinstance(data["messages"], Sequence):
        user_messages = list(_iter_user_messages(data["messages"]))
        if user_messages:
            return "\n".join(user_messages)
    prompt_value = data.get("prompt")
    if isinstance(prompt_value, str) and prompt_value:
        return prompt_value
    return None


def extract_prompt(content: Any) -> PromptExtractionResult:
    """Normalise ``content`` into a prompt string.

    Parameters
    ----------
    content:
        The raw ``content`` value received from the event payload.  Supported
        structures include raw strings, JSON strings, dictionaries with
        ``messages`` and ``prompt`` keys, as well as sequences of user messages.

    Returns
    -------
    PromptExtractionResult
        The structured result containing the prompt string.

    Raises
    ------
    ValidationError
        If the content cannot be converted into a textual prompt.
    """

    prompt_text: str | None = None
    details: str | None = None

    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            prompt_text = content
        else:
            prompt_text = _prompt_from_parsed_content(parsed)
            details = "content JSON string"
    elif _is_mapping(content):
        prompt_text = _prompt_from_mapping(content)
        details = "content mapping"
    elif isinstance(content, Sequence) and not isinstance(content, (bytes, bytearray)):
        prompt_text = _prompt_from_sequence(content)
        details = "content sequence"
    else:
        prompt_text = str(content) if content is not None else None
        details = "content coerced to string"

    if isinstance(prompt_text, str) and prompt_text.strip():
        return PromptExtractionResult(prompt=prompt_text)

    raise ValidationError(
        code="prompt_extraction_failed",
        message="Could not derive a valid prompt from content.",
        status_code=422,
        details=details,
    )


def _prompt_from_sequence(items: Sequence[Any]) -> str | None:
    user_messages: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            user_messages.append(item)
        elif _is_mapping(item):
            maybe = _prompt_from_mapping(item)
            if maybe:
                user_messages.append(maybe)
    if user_messages:
        return "\n".join(user_messages)
    return None


def _prompt_from_parsed_content(parsed: Any) -> str | None:
    if isinstance(parsed, str):
        return parsed
    if _is_mapping(parsed):
        maybe = _prompt_from_mapping(parsed)
        if maybe:
            return maybe
        return json.dumps(parsed)
    if isinstance(parsed, Sequence) and not isinstance(parsed, (bytes, bytearray)):
        maybe = _prompt_from_sequence(parsed)
        if maybe:
            return maybe
    return json.dumps(parsed)


__all__ = ["PromptExtractionResult", "extract_prompt"]
