import pytest
from unittest.mock import MagicMock

import requests

from ai_ticket.backends.kobold_client import KoboldCompletionResult, get_kobold_completion


@pytest.fixture(autouse=True)
def _no_sleep(mocker):
    return mocker.patch("ai_ticket.backends.kobold_client.time.sleep")


@pytest.fixture
def mock_requests_post(mocker):
    return mocker.patch("requests.post")


def test_get_kobold_completion_success_chat_completions(mock_requests_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": " Test completion "}}]
    }
    mock_requests_post.return_value = mock_response

    result = get_kobold_completion("Test prompt")

    assert isinstance(result, KoboldCompletionResult)
    assert result.completion == "Test completion"
    assert result.error is None

    expected_url = "http://localhost:5001/api/v1/chat/completions"
    mock_requests_post.assert_called_once()
    args, kwargs = mock_requests_post.call_args
    assert args[0] == expected_url
    assert kwargs["json"]["messages"][0]["content"] == "Test prompt"


def test_get_kobold_completion_success_plain_completions_fallback(mock_requests_post):
    mock_chat_fail_response = MagicMock()
    http_error = requests.exceptions.HTTPError("Simulated HTTP Error")
    mock_chat_fail_response.raise_for_status.side_effect = http_error

    mock_plain_success_response = MagicMock()
    mock_plain_success_response.status_code = 200
    mock_plain_success_response.json.return_value = {
        "choices": [{"text": " Fallback completion "}]
    }

    mock_requests_post.side_effect = [
        mock_chat_fail_response,
        mock_plain_success_response,
    ]

    result = get_kobold_completion("Test prompt for fallback")

    assert isinstance(result, KoboldCompletionResult)
    assert result.completion == "Fallback completion"

    assert mock_requests_post.call_count == 2

    args_chat, kwargs_chat = mock_requests_post.call_args_list[0]
    assert args_chat[0] == "http://localhost:5001/api/v1/chat/completions"
    assert kwargs_chat["json"]["messages"][0]["content"] == "Test prompt for fallback"

    args_plain, kwargs_plain = mock_requests_post.call_args_list[1]
    assert args_plain[0] == "http://localhost:5001/api/v1/completions"
    assert kwargs_plain["json"]["prompt"] == "Test prompt for fallback"


def test_get_kobold_completion_all_fallbacks_fail(mock_requests_post):
    mock_requests_post.side_effect = requests.exceptions.RequestException("Simulated network error")

    result = get_kobold_completion("Test prompt all fail")

    assert isinstance(result, KoboldCompletionResult)
    assert result.completion is None
    assert result.error == "api_request_error"
    assert mock_requests_post.call_count == 2


def test_get_kobold_completion_custom_url(mock_requests_post, monkeypatch):
    custom_url = "http://mykobold.ai:1234/customapi"
    monkeypatch.setenv("KOBOLDCPP_API_URL", custom_url)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Custom URL works"}}]
    }
    mock_requests_post.return_value = mock_response

    result = get_kobold_completion("Test prompt custom URL")

    assert isinstance(result, KoboldCompletionResult)
    assert result.completion == "Custom URL works"

    expected_url_chat = f"{custom_url.rstrip('/')}/v1/chat/completions"
    mock_requests_post.assert_called_once()
    args, kwargs = mock_requests_post.call_args
    assert args[0] == expected_url_chat

    monkeypatch.delenv("KOBOLDCPP_API_URL", raising=False)
