import json

import pytest

from ai_ticket.backends.kobold_client import KoboldCompletionResult
from ai_ticket.events.inference import CompletionResponse, ErrorResponse, on_event


@pytest.fixture
def mock_get_kobold_completion(mocker):
    return mocker.patch("ai_ticket.events.inference.get_kobold_completion")


def test_on_event_simple_prompt_success(mock_get_kobold_completion):
    mock_get_kobold_completion.return_value = KoboldCompletionResult(completion="Mocked completion")

    event_data = {"content": "Hello Kobold"}
    result = on_event(event_data)

    assert isinstance(result, CompletionResponse)
    assert result.completion == "Mocked completion"
    mock_get_kobold_completion.assert_called_once_with(prompt="Hello Kobold")


def test_on_event_json_prompt_messages_success(mock_get_kobold_completion):
    mock_get_kobold_completion.return_value = KoboldCompletionResult(completion="JSON completion")

    json_content = json.dumps(
        {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Tell me a joke."},
            ]
        }
    )
    event_data = {"content": json_content}
    result = on_event(event_data)

    assert isinstance(result, CompletionResponse)
    assert result.completion == "JSON completion"
    mock_get_kobold_completion.assert_called_once_with(prompt="Tell me a joke.")


def test_on_event_json_prompt_direct_success(mock_get_kobold_completion):
    mock_get_kobold_completion.return_value = KoboldCompletionResult(completion="Direct JSON prompt completion")

    json_content = json.dumps({"prompt": "Direct prompt here"})
    event_data = {"content": json_content}
    result = on_event(event_data)

    assert isinstance(result, CompletionResponse)
    assert result.completion == "Direct JSON prompt completion"
    mock_get_kobold_completion.assert_called_once_with(prompt="Direct prompt here")


def test_on_event_no_content(mock_get_kobold_completion):
    event_data = {}
    result = on_event(event_data)

    assert isinstance(result, ErrorResponse)
    assert result.error == "missing_content_field"
    assert result.status_code == 400
    mock_get_kobold_completion.assert_not_called()


def test_on_event_prompt_extraction_failure(mock_get_kobold_completion):
    event_data = {"content": {"messages": []}}
    result = on_event(event_data)

    assert isinstance(result, ErrorResponse)
    assert result.error == "prompt_extraction_failed"
    assert result.status_code == 422
    mock_get_kobold_completion.assert_not_called()


def test_on_event_backend_failure(mock_get_kobold_completion):
    mock_get_kobold_completion.return_value = KoboldCompletionResult(
        error="api_failure",
        details="boom",
    )

    event_data = {"content": "A prompt that will fail"}
    result = on_event(event_data)

    assert isinstance(result, ErrorResponse)
    assert result.error == "api_failure"
    assert result.status_code == 502
    assert result.details == "boom"
    mock_get_kobold_completion.assert_called_once_with(prompt="A prompt that will fail")
