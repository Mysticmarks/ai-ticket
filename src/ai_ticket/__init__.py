"""Public package helpers."""

from __future__ import annotations

import re
from typing import Final


_SYSTEM_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(```)?\s*{\s*\"messages\"\s*:\s*\[\s*{\s*\"role\"\s*:\s*\"system\"\s*,\s*\"content\"\s*:\s*\"You\s+are\s+(?P<name>[^,]+),",
    flags=re.IGNORECASE | re.DOTALL,
)


def find_name(text: object) -> str | None:
    """Extract the assistant name from a system prompt blob.

    The historical implementation attempted to use a positional capture group
    that never existed, which meant the function always raised ``IndexError``
    or returned ``False``.  We now gracefully handle non-string inputs and only
    return a stripped name when the expression matches.
    """

    if not isinstance(text, str):
        return None

    match = _SYSTEM_NAME_PATTERN.search(text)
    if not match:
        return None

    extracted_name = match.group("name").strip()
    return extracted_name or None


__all__ = ["find_name"]
