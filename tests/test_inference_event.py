import json
from unittest.mock import patch

import pytest

from ai_ticket.events.inference import on_event


@pytest.fixture
def mock_get_kobold_completion():
    with patch('ai_ticket.events.inference.get_kobold_completion') as mock:
        yield mock


def test_on_event_simple_prompt_success(mock_get_kobold_completion):
    mock_get_kobold_completion.return_value = {"completion": "Mocked completion"}

    event_data = {"content": "Hello Kobold"}
    result = on_event(event_data)

    assert result == {"completion": "Mocked completion"}
    mock_get_kobold_completion.assert_called_once_with(prompt="Hello Kobold")


def test_on_event_json_prompt_messages_success(mock_get_kobold_completion):
    mock_get_kobold_completion.return_value = {"completion": "JSON completion"}

    json_content = json.dumps({
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Tell me a joke."}
        ]
    })
    event_data = {"content": json_content}
    result = on_event(event_data)

    assert result == {"completion": "JSON completion"}
    # The on_event function joins user messages with newline
    mock_get_kobold_completion.assert_called_once_with(prompt="Tell me a joke.")


def test_on_event_json_prompt_direct_success(mock_get_kobold_completion):
    mock_get_kobold_completion.return_value = {"completion": "Direct JSON prompt completion"}

    json_content = json.dumps({"prompt": "Direct prompt here"})
    event_data = {"content": json_content}
    result = on_event(event_data)

    assert result == {"completion": "Direct JSON prompt completion"}
    mock_get_kobold_completion.assert_called_once_with(prompt="Direct prompt here")


def test_on_event_no_content(mock_get_kobold_completion):
    event_data = {}
    result = on_event(event_data)
    assert result["error"] == "missing_content_field"
    assert "'content' field is missing" in result["details"]
    mock_get_kobold_completion.assert_not_called()


def test_on_event_empty_prompt_after_parse(mock_get_kobold_completion):
    # e.g. JSON with messages but no user messages
    json_content = json.dumps({"messages": [{"role": "system", "content": "System only"}]})
    event_data = {"content": json_content}
    mock_get_kobold_completion.return_value = {
        "error": "prompt_extraction_failed",
        "details": "Could not extract a valid prompt",
    }
    result = on_event(event_data)
    assert result["error"] == "prompt_extraction_failed"
    mock_get_kobold_completion.assert_called_once()


def test_on_event_kobold_fails(mock_get_kobold_completion):
    mock_get_kobold_completion.return_value = {"error": "Failed to get completion from KoboldCPP."}

    event_data = {"content": "A prompt that will fail"}
    result = on_event(event_data)

    assert result == {"error": "Failed to get completion from KoboldCPP."}
    mock_get_kobold_completion.assert_called_once_with(prompt="A prompt that will fail")
