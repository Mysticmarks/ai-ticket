import json

import pytest

from ai_ticket.events.inference import on_event

# Use mocker fixture from pytest-mock
@pytest.fixture
def mock_get_kobold_completion(mocker):
    return mocker.patch('ai_ticket.events.inference.get_kobold_completion')

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


def test_on_event_json_string_payload(mock_get_kobold_completion):
    mock_get_kobold_completion.return_value = {"completion": "String payload"}

    json_content = json.dumps("simple")
    event_data = {"content": json_content}
    result = on_event(event_data)

    assert result == {"completion": "String payload"}
    mock_get_kobold_completion.assert_called_once_with(prompt="simple")


def test_on_event_json_list_payload(mock_get_kobold_completion):
    mock_get_kobold_completion.return_value = {"completion": "List payload"}

    json_content = json.dumps(["first", "second"])
    event_data = {"content": json_content}
    result = on_event(event_data)

    assert result == {"completion": "List payload"}
    mock_get_kobold_completion.assert_called_once_with(prompt='["first", "second"]')

def test_on_event_no_content(mock_get_kobold_completion):
    event_data = {}
    result = on_event(event_data)
    assert result == {
        "error": "missing_content_field",
        "details": "'content' field is missing in event data.",
    }
    mock_get_kobold_completion.assert_not_called()

def test_on_event_empty_prompt_after_parse(mock_get_kobold_completion):
    # e.g. JSON with messages but no user messages
    json_content = json.dumps({"messages": [{"role": "system", "content": "System only"}]})
    event_data = {"content": json_content}
    result = on_event(event_data)
    assert result == {
        "error": "prompt_extraction_failed",
        "details": "Could not derive a valid string prompt from 'content'.",
    }
    mock_get_kobold_completion.assert_not_called()


def test_on_event_kobold_fails(mock_get_kobold_completion):
    mock_get_kobold_completion.return_value = {
        "error": "api_connection_error",
        "details": "Failed to connect",
    }

    event_data = {"content": "A prompt that will fail"}
    result = on_event(event_data)

    assert result == {
        "error": "api_connection_error",
        "details": "Failed to connect",
    }
    mock_get_kobold_completion.assert_called_once_with(prompt="A prompt that will fail")


def test_on_event_invalid_input_type(mock_get_kobold_completion):
    result = on_event(["not", "a", "dict"])

    assert result == {
        "error": "invalid_input_format",
        "details": "Event data must be a dictionary.",
    }
    mock_get_kobold_completion.assert_not_called()


def test_on_event_handles_type_error(mock_get_kobold_completion):
    mock_get_kobold_completion.return_value = {"completion": "Converted"}

    event_data = {"content": {"prompt": "value"}}
    result = on_event(event_data)

    assert result == {"completion": "Converted"}
    mock_get_kobold_completion.assert_called_once_with(prompt="{'prompt': 'value'}")


def test_on_event_missing_backend_details(mock_get_kobold_completion):
    mock_get_kobold_completion.return_value = {"error": "api_unknown_error"}

    event_data = {"content": "Prompt"}
    result = on_event(event_data)

    assert result == {
        "error": "api_unknown_error",
        "details": "Failed to get completion from KoboldCPP.",
    }
    mock_get_kobold_completion.assert_called_once_with(prompt="Prompt")

# Remove or update the old test_find_name.py as find_name is no longer central.
# For now, we'll leave test_find_name.py as is, since it tests a different utility function.
# The plan is to focus on KoboldCPP integration.