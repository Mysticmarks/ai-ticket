from unittest.mock import MagicMock

import pytest
import requests
import json

from ai_ticket.backends import kobold_client


@pytest.fixture(autouse=True)
def set_default_url(monkeypatch):
    monkeypatch.setenv("KOBOLDCPP_API_URL", "http://localhost:5001/api")


@pytest.fixture
def mock_requests_post(mocker):
    return mocker.patch("ai_ticket.backends.kobold_client.requests.post")


@pytest.fixture
def fast_sleep(mocker):
    return mocker.patch("ai_ticket.backends.kobold_client.time.sleep")


def _http_error(status_code: int, text: str = "error", headers: dict | None = None):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.headers = headers or {}
    error = requests.exceptions.HTTPError(text)
    error.response = response
    return error


def test_get_kobold_completion_success_chat(mock_requests_post):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "choices": [{"message": {"content": " Test completion "}}]
    }
    mock_requests_post.return_value = mock_response

    result = kobold_client.get_kobold_completion("Test prompt")

    assert result == {"completion": "Test completion"}
    mock_requests_post.assert_called_once()
    url, = mock_requests_post.call_args[0]
    assert url.endswith("/v1/chat/completions")


def test_get_kobold_completion_falls_back_to_plain_endpoint(mock_requests_post, fast_sleep):
    chat_error_response = MagicMock()
    chat_error_response.raise_for_status.side_effect = [
        _http_error(500),
        _http_error(500),
        _http_error(500),
    ]

    plain_success_response = MagicMock()
    plain_success_response.raise_for_status.return_value = None
    plain_success_response.json.return_value = {
        "choices": [{"text": " Plain completion "}]
    }

    mock_requests_post.side_effect = [
        chat_error_response,
        chat_error_response,
        chat_error_response,
        plain_success_response,
    ]

    result = kobold_client.get_kobold_completion("Prompt needing fallback")

    assert result == {"completion": "Plain completion"}
    assert mock_requests_post.call_count == 4
    urls = [call_args[0][0] for call_args in mock_requests_post.call_args_list]
    assert urls.count("http://localhost:5001/api/v1/chat/completions") == 3
    assert urls[-1] == "http://localhost:5001/api/v1/completions"


def test_get_kobold_completion_times_out_then_succeeds(mock_requests_post, fast_sleep):
    timeout_error = requests.exceptions.Timeout("timeout")

    chat_timeout_response = MagicMock()
    chat_timeout_response.raise_for_status.side_effect = timeout_error

    success_response = MagicMock()
    success_response.raise_for_status.return_value = None
    success_response.json.return_value = {
        "choices": [{"message": {"content": " Recovered completion "}}]
    }

    mock_requests_post.side_effect = [
        timeout_error,
        timeout_error,
        success_response,
    ]

    result = kobold_client.get_kobold_completion("Retry prompt")

    assert result == {"completion": "Recovered completion"}
    assert mock_requests_post.call_count == 3


def test_get_kobold_completion_exhausts_retries(mock_requests_post, fast_sleep):
    timeout_error = requests.exceptions.Timeout("timeout")
    mock_requests_post.side_effect = [timeout_error] * 6

    result = kobold_client.get_kobold_completion("Failing prompt")

    assert result == {
        "error": "api_connection_error",
        "details": "Failed to connect to KoboldCPP API after multiple attempts. Last error: timeout",
    }
    assert mock_requests_post.call_count == 6


def test_get_kobold_completion_configuration_error(monkeypatch):
    monkeypatch.delenv("KOBOLDCPP_API_URL", raising=False)

    result = kobold_client.get_kobold_completion("Prompt")

    assert result == {
        "error": "configuration_error",
        "details": "KOBOLDCPP_API_URL is not set.",
    }


def test_get_kobold_completion_auth_error(mock_requests_post):
    auth_error = _http_error(401)
    response = MagicMock()
    response.raise_for_status.side_effect = auth_error
    mock_requests_post.return_value = response

    result = kobold_client.get_kobold_completion("Prompt")

    assert result == {
        "error": "api_authentication_error",
        "details": "KoboldCPP API request failed due to authentication/authorization (chat endpoint). Status: 401",
    }


def test_get_kobold_completion_rate_limit_retry(mock_requests_post, fast_sleep):
    rate_limit_error = _http_error(429, headers={"Retry-After": "2"})
    first_response = MagicMock()
    first_response.raise_for_status.side_effect = rate_limit_error

    second_response = MagicMock()
    second_response.raise_for_status.return_value = None
    second_response.json.return_value = {
        "choices": [{"message": {"content": " Final completion "}}]
    }

    mock_requests_post.side_effect = [first_response, second_response]

    result = kobold_client.get_kobold_completion("Prompt")

    assert result == {"completion": "Final completion"}
    fast_sleep.assert_any_call(2)


def test_get_kobold_completion_client_error(mock_requests_post):
    client_error = _http_error(404, text="missing")
    response = MagicMock()
    response.raise_for_status.side_effect = client_error
    mock_requests_post.return_value = response

    result = kobold_client.get_kobold_completion("Prompt")

    assert result["error"] == "api_client_error"
    assert "Status: 404" in result["details"]


def test_get_kobold_completion_json_decode_error(mock_requests_post):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.side_effect = json.JSONDecodeError("msg", "doc", 0)
    response.text = "invalid json"
    mock_requests_post.return_value = response

    result = kobold_client.get_kobold_completion("Prompt")

    assert result["error"] == "api_response_format_error"
    assert "Failed to decode JSON" in result["details"]


def test_get_kobold_completion_structure_error(mock_requests_post):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": []}
    mock_requests_post.return_value = response

    result = kobold_client.get_kobold_completion("Prompt")

    assert result["error"] == "api_response_structure_error"


def test_get_kobold_completion_request_exception(mock_requests_post):
    mock_requests_post.side_effect = [requests.exceptions.RequestException("boom")]

    result = kobold_client.get_kobold_completion("Prompt")

    assert result["error"] == "api_request_error"
