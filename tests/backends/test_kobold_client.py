import pytest
import os
from unittest.mock import MagicMock, call # Using unittest.mock directly as pytest-mock just wraps it
from ai_ticket.backends import kobold_client

@pytest.fixture
def mock_requests_post(mocker): # pytest-mock provides 'mocker' fixture
    return mocker.patch('requests.post')

def test_get_kobold_completion_success_chat_completions(mock_requests_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": " Test completion "}}]
    }
    mock_requests_post.return_value = mock_response

    completion = kobold_client.get_kobold_completion("Test prompt")
    assert completion == "Test completion"

    expected_url = "http://localhost:5001/api/v1/chat/completions"
    mock_requests_post.assert_called_once()
    args, kwargs = mock_requests_post.call_args
    assert args[0] == expected_url
    assert kwargs['json']['messages'][0]['content'] == "Test prompt"

def test_get_kobold_completion_success_plain_completions_fallback(mock_requests_post):
    # Simulate chat endpoint failing, then plain endpoint succeeding
    mock_chat_fail_response = MagicMock()
    mock_chat_fail_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Simulated HTTP Error")

    mock_plain_success_response = MagicMock()
    mock_plain_success_response.status_code = 200
    mock_plain_success_response.json.return_value = {
        "choices": [{"text": " Fallback completion "}]
    }

    # Configure responses for sequential calls
    mock_requests_post.side_effect = [
        mock_chat_fail_response,
        mock_plain_success_response
    ]

    completion = kobold_client.get_kobold_completion("Test prompt for fallback")
    assert completion == "Fallback completion"

    assert mock_requests_post.call_count == 2

    # Check first call (chat completions)
    call_args_chat = mock_requests_post.call_args_list[0]
    args_chat, kwargs_chat = call_args_chat
    assert args_chat[0] == "http://localhost:5001/api/v1/chat/completions"
    assert kwargs_chat['json']['messages'][0]['content'] == "Test prompt for fallback"

    # Check second call (plain completions)
    call_args_plain = mock_requests_post.call_args_list[1]
    args_plain, kwargs_plain = call_args_plain
    assert args_plain[0] == "http://localhost:5001/api/v1/completions"
    assert kwargs_plain['json']['prompt'] == "Test prompt for fallback"


def test_get_kobold_completion_all_fallbacks_fail(mock_requests_post):
    mock_requests_post.side_effect = requests.exceptions.RequestException("Simulated network error")

    completion = kobold_client.get_kobold_completion("Test prompt all fail")
    assert completion is None
    assert mock_requests_post.call_count == 2 # Both chat and plain endpoints were tried

def test_get_kobold_completion_custom_url(mock_requests_post, monkeypatch):
    custom_url = "http://mykobold.ai:1234/customapi"
    # Using monkeypatch from pytest to set environment variable
    monkeypatch.setenv("KOBOLDCPP_API_URL", custom_url)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "Custom URL works"}}]}
    mock_requests_post.return_value = mock_response

    completion = kobold_client.get_kobold_completion("Test prompt custom URL")
    assert completion == "Custom URL works"

    expected_url_chat = f"{custom_url.rstrip('/')}/v1/chat/completions"
    mock_requests_post.assert_called_once()
    args, kwargs = mock_requests_post.call_args
    assert args[0] == expected_url_chat

    # Clean up env var if necessary, though monkeypatch handles it for this test
    monkeypatch.delenv("KOBOLDCPP_API_URL", raising=False)

# Need to import requests for the side_effect
import requests
