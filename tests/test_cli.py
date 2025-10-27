from __future__ import annotations

import argparse
from unittest import mock

import pytest

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
