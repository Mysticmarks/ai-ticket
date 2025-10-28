from __future__ import annotations

import argparse
import json
from unittest import mock

import pytest
import requests

from ai_ticket import cli


def _make_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "host": "0.0.0.0",
        "port": 5000,
        "reload": False,
        "workers": 2,
        "worker_class": "gthread",
        "threads": 4,
        "timeout": 30,
        "keepalive": 5,
        "graceful_timeout": 30,
        "access_log": "-",
        "error_log": "-",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _make_prompt_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "server_url": "http://example.com",
        "prompt_text": "Hello world",
        "temperature": 0.7,
        "max_tokens": 128,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.fixture()
def cli_context() -> cli._CLIContext:  # type: ignore[attr-defined]
    return cli._CLIContext(accent="cyan")  # type: ignore[attr-defined]


def test_serve_command_runs_gunicorn_by_default(mocker, cli_context) -> None:
    mocker.patch("ai_ticket.cli._print_panel")
    flask_app = mock.Mock()
    mocker.patch("ai_ticket.cli._load_flask_app", return_value=flask_app)
    run_with_gunicorn = mocker.patch("ai_ticket.cli._run_with_gunicorn")

    args = _make_args()

    result = cli._serve_command(args, cli_context)  # type: ignore[attr-defined]

    assert result == 0
    run_with_gunicorn.assert_called_once()
    call_app, options = run_with_gunicorn.call_args[0]
    assert call_app is flask_app
    assert options["bind"] == "0.0.0.0:5000"
    assert options["workers"] == args.workers
    assert options["worker_class"] == args.worker_class


def test_serve_command_uses_flask_reloader_when_requested(mocker, cli_context) -> None:
    mocker.patch("ai_ticket.cli._print_panel")
    flask_app = mock.Mock()
    mocker.patch("ai_ticket.cli._load_flask_app", return_value=flask_app)
    run_with_flask = mocker.patch("ai_ticket.cli._run_with_flask_reload")
    run_with_gunicorn = mocker.patch("ai_ticket.cli._run_with_gunicorn")

    args = _make_args(reload=True, host="127.0.0.1", port=9000)

    result = cli._serve_command(args, cli_context)  # type: ignore[attr-defined]

    assert result == 0
    run_with_flask.assert_called_once_with(flask_app, "127.0.0.1", 9000)
    run_with_gunicorn.assert_not_called()


def test_serve_command_reports_missing_gunicorn(mocker, cli_context) -> None:
    mocker.patch("ai_ticket.cli._print_panel")
    mocker.patch("ai_ticket.cli._load_flask_app", return_value=mock.Mock())
    mocker.patch("ai_ticket.cli._run_with_gunicorn", side_effect=ImportError("gunicorn"))

    args = _make_args()

    result = cli._serve_command(args, cli_context)  # type: ignore[attr-defined]

    assert result == 1


@pytest.mark.failure_mode
def test_prompt_command_handles_network_failure(mocker, cli_context) -> None:
    args = _make_prompt_args()
    print_panel = mocker.patch("ai_ticket.cli._print_panel")
    mocker.patch(
        "ai_ticket.cli.requests.post",
        side_effect=requests.RequestException("boom"),
    )

    result = cli._prompt_command(args, cli_context)  # type: ignore[attr-defined]

    assert result == 1
    print_panel.assert_any_call("Prompt", mock.ANY, "red")
    assert any(
        "Failed to contact service" in call.args[1]
        for call in print_panel.call_args_list
    )


@pytest.mark.failure_mode
def test_prompt_command_handles_service_error(mocker, cli_context) -> None:
    args = _make_prompt_args()
    print_panel = mocker.patch("ai_ticket.cli._print_panel")
    response = mock.Mock()
    response.status_code = 503
    response.json.return_value = {"details": "offline"}
    response.text = ""
    mocker.patch("ai_ticket.cli.requests.post", return_value=response)

    result = cli._prompt_command(args, cli_context)  # type: ignore[attr-defined]

    assert result == 1
    print_panel.assert_any_call("Prompt", mock.ANY, "red")
    assert any(
        "Service returned 503" in call.args[1]
        for call in print_panel.call_args_list
    )


@pytest.mark.failure_mode
def test_prompt_command_handles_invalid_json_response(mocker, cli_context) -> None:
    args = _make_prompt_args()
    print_panel = mocker.patch("ai_ticket.cli._print_panel")
    response = mock.Mock()
    response.status_code = 200
    response.json.side_effect = json.JSONDecodeError("msg", "", 0)
    response.text = "not json"
    mocker.patch("ai_ticket.cli.requests.post", return_value=response)

    result = cli._prompt_command(args, cli_context)  # type: ignore[attr-defined]

    assert result == 1
    print_panel.assert_any_call("Prompt", mock.ANY, "red")
    assert any(
        "Invalid JSON payload" in call.args[1]
        for call in print_panel.call_args_list
    )
