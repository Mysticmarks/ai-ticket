import json

import pytest

from ai_ticket.events.prompt_extraction import PromptExtractionResult, extract_prompt
from ai_ticket.events.validation import ValidationError


def test_extract_prompt_from_raw_string():
    result = extract_prompt("Just a prompt")
    assert isinstance(result, PromptExtractionResult)
    assert result.prompt == "Just a prompt"


def test_extract_prompt_from_json_messages():
    payload = json.dumps(
        {
            "messages": [
                {"role": "system", "content": "ignore"},
                {"role": "user", "content": "First"},
                {"role": "user", "content": "Second"},
            ]
        }
    )
    result = extract_prompt(payload)
    assert result.prompt == "First\nSecond"


def test_extract_prompt_from_json_prompt_field():
    payload = json.dumps({"prompt": "From JSON"})
    result = extract_prompt(payload)
    assert result.prompt == "From JSON"


def test_extract_prompt_invalid_content_raises():
    with pytest.raises(ValidationError) as exc_info:
        extract_prompt({"messages": []})

    assert exc_info.value.code == "prompt_extraction_failed"
