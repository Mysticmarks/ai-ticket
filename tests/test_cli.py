from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from ai_ticket import cli


class MockResponse:
    def __init__(self, *, status_code: int, json_data: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self) -> Any:
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


def test_prompt_success(capsys: pytest.CaptureFixture[str]) -> None:
    response = MockResponse(status_code=200, json_data={"completion": "All tickets resolved."})
    with patch("requests.post", return_value=response) as mock_post:
        exit_code = cli.main(["prompt", "Resolve tickets"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert mock_post.called
    assert "Completion" in captured.out
    assert "All tickets resolved." in captured.out


def test_prompt_backend_error(capsys: pytest.CaptureFixture[str]) -> None:
    response = MockResponse(status_code=502, json_data={"error": "backend_error", "message": "Failed"})
    with patch("requests.post", return_value=response):
        exit_code = cli.main(["prompt", "Hello there"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Service returned 502" in captured.out


def test_prompt_invalid_json(capsys: pytest.CaptureFixture[str]) -> None:
    response = MockResponse(status_code=200, json_data=json.JSONDecodeError("x", "y", 0))
    with patch("requests.post", return_value=response):
        exit_code = cli.main(["prompt", "Test"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Invalid JSON" in captured.out


def test_health_success(capsys: pytest.CaptureFixture[str]) -> None:
    response = MockResponse(status_code=200, json_data={"status": "healthy"})
    with patch("requests.get", return_value=response) as mock_get:
        exit_code = cli.main(["health"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert mock_get.called
    assert "HTTP 200" in captured.out
    assert "healthy" in captured.out


def test_health_failure(capsys: pytest.CaptureFixture[str]) -> None:
    response = MockResponse(status_code=503, json_data={"status": "degraded"})
    with patch("requests.get", return_value=response):
        exit_code = cli.main(["health"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "HTTP 503" in captured.out
    assert "degraded" in captured.out


def test_health_json_error(capsys: pytest.CaptureFixture[str]) -> None:
    response = MockResponse(status_code=200, json_data=json.JSONDecodeError("err", "doc", 0), text="oops")
    with patch("requests.get", return_value=response):
        exit_code = cli.main(["health"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "oops" in captured.out
