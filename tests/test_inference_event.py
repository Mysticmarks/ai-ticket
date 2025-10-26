import pytest
import json
from ai_ticket.events.inference import on_event


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
    mock_get_kobold_completion.assert_not_called()


def test_on_event_empty_prompt_after_parse(mock_get_kobold_completion):
    mock_get_kobold_completion.return_value = {"completion": "System context"}
    message_payload = {"messages": [{"role": "system", "content": "System only"}]}
    json_content = json.dumps(message_payload)
    event_data = {"content": json_content}
    result = on_event(event_data)
    assert result == {"completion": "System context"}
    mock_get_kobold_completion.assert_called_once_with(prompt=json.dumps(message_payload))


def test_on_event_kobold_fails(mock_get_kobold_completion):
    mock_get_kobold_completion.return_value = {"error": "api_connection_error"}

    event_data = {"content": "A prompt that will fail"}
    result = on_event(event_data)

    assert result == {"error": "api_connection_error"}
    mock_get_kobold_completion.assert_called_once_with(prompt="A prompt that will fail")

# Remove or update the old test_find_name.py as find_name is no longer central.
# For now, we'll leave test_find_name.py as is, since it tests a different utility function.
# The plan is to focus on KoboldCPP integration.