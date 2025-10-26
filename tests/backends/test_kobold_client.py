import os
from unittest.mock import MagicMock, call # Using unittest.mock directly as pytest-mock just wraps it

import pytest

from ai_ticket.backends import kobold_client


@pytest.fixture
def mock_requests_post(mocker):
    return mocker.patch('requests.post')


@pytest.fixture(autouse=True)
def ensure_api_url(monkeypatch):
    monkeypatch.setenv("KOBOLDCPP_API_URL", "http://localhost:5001/api")


def test_get_kobold_completion_success_chat_completions(mock_requests_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": " Test completion "}}]
    }
    mock_requests_post.return_value = mock_response

    completion = kobold_client.get_kobold_completion("Test prompt")
    assert completion == {"completion": "Test completion"}

    expected_url = "http://localhost:5001/api/v1/chat/completions"
    mock_requests_post.assert_called_once()
    args, kwargs = mock_requests_post.call_args
    assert args[0] == expected_url
    assert kwargs['json']['messages'][0]['content'] == "Test prompt"

def test_get_kobold_completion_success_plain_completions_fallback(mock_requests_post):
    # Simulate chat endpoint failing, then plain endpoint succeeding
    mock_plain_success_response = MagicMock()
    mock_plain_success_response.status_code = 200
    mock_plain_success_response.raise_for_status.return_value = None
    mock_plain_success_response.json.return_value = {
        "choices": [{"text": " Fallback completion "}]
    }

    def side_effect(url, *args, **kwargs):
        if url.endswith("/v1/chat/completions"):
            failure = MagicMock()
            http_error = requests.exceptions.HTTPError("Simulated HTTP Error")
            http_error.response = MagicMock(status_code=500, text="")
            failure.raise_for_status.side_effect = http_error
            return failure
        return mock_plain_success_response

    mock_requests_post.side_effect = side_effect

    completion = kobold_client.get_kobold_completion("Test prompt for fallback")
    assert completion == {"completion": "Fallback completion"}

    assert mock_requests_post.call_count >= 2

    # First request should target the chat endpoint
    args_chat, kwargs_chat = mock_requests_post.call_args_list[0]
    assert args_chat[0] == "http://localhost:5001/api/v1/chat/completions"
    assert kwargs_chat['json']['messages'][0]['content'] == "Test prompt for fallback"

    # Last request should target the plain completions endpoint
    args_plain, kwargs_plain = mock_requests_post.call_args_list[-1]
    assert args_plain[0] == "http://localhost:5001/api/v1/completions"
    assert kwargs_plain['json']['prompt'] == "Test prompt for fallback"


def test_get_kobold_completion_all_fallbacks_fail(mock_requests_post):
    mock_requests_post.side_effect = requests.exceptions.RequestException("Simulated network error")

    completion = kobold_client.get_kobold_completion("Test prompt all fail")
    assert completion["error"] in {"api_connection_error", "api_request_error"}
    assert mock_requests_post.call_count == 1

def test_get_kobold_completion_custom_url(mock_requests_post, monkeypatch):
    custom_url = "http://mykobold.ai:1234/customapi"
    # Using monkeypatch from pytest to set environment variable
    monkeypatch.setenv("KOBOLDCPP_API_URL", custom_url)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "Custom URL works"}}]}
    mock_requests_post.return_value = mock_response

    completion = kobold_client.get_kobold_completion("Test prompt custom URL")
    assert completion == {"completion": "Custom URL works"}

    expected_url_chat = f"{custom_url.rstrip('/')}/v1/chat/completions"
    mock_requests_post.assert_called_once()
    args, kwargs = mock_requests_post.call_args
    assert args[0] == expected_url_chat

    # Clean up env var if necessary, though monkeypatch handles it for this test
    monkeypatch.delenv("KOBOLDCPP_API_URL", raising=False)

# Need to import requests for the side_effect
import requests
