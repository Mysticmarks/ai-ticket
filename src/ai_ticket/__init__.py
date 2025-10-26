"""Public package exports."""

import re
from typing import Optional

_NAME_PATTERN = re.compile(r'"content"\s*:\s*"You\s+are\s+([^,"]+)')


def find_name(text: Optional[str]):
    """Extract the agent name from the system message payload."""

    if not text or not isinstance(text, str):
        return False

    match = _NAME_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return None
