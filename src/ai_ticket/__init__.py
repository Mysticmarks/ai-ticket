"""Utility helpers for the ai_ticket package."""

import re

_NAME_PATTERN = re.compile(r"You\s+are\s+(?P<name>[^,\n]+)", re.IGNORECASE)


def find_name(text):
    """Extract the assistant persona name from a structured prompt string."""

    if not isinstance(text, str) or not text:
        return False

    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        stripped = stripped[3:-3].strip()

    match = _NAME_PATTERN.search(stripped)
    if match:
        return match.group("name").strip()
    return None
