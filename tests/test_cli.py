from __future__ import annotations

import argparse

import pytest

from ai_ticket import cli


def _make_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "host": "0.0.0.0",
        "port": 5000,
        "reload": False,
        "workers": 4,
        "keepalive": 5,
        "limit_concurrency": 1000,
        "backlog": 2048,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.fixture()
def cli_context() -> cli._CLIContext:  # type: ignore[attr-defined]
    return cli._CLIContext(accent="cyan")  # type: ignore[attr-defined]


def test_serve_command_runs_uvicorn_by_default(mocker, cli_context) -> None:
    mock_print = mocker.patch("ai_ticket.cli._print_panel")
    run_with_uvicorn = mocker.patch("ai_ticket.cli._run_with_uvicorn")

    args = _make_args()

    result = cli._serve_command(args, cli_context)  # type: ignore[attr-defined]

    assert result == 0
    run_with_uvicorn.assert_called_once()
    options = run_with_uvicorn.call_args[0][0]
    assert options["host"] == "0.0.0.0"
    assert options["port"] == 5000
    assert options["workers"] == 4
    assert options["limit_concurrency"] == 1000
    assert options["backlog"] == 2048
    assert options["reload"] is False
    mock_print.assert_called_once()


def test_serve_command_enables_reload(mocker, cli_context) -> None:
    mock_print = mocker.patch("ai_ticket.cli._print_panel")
    run_with_uvicorn = mocker.patch("ai_ticket.cli._run_with_uvicorn")

    args = _make_args(reload=True, workers=8)

    result = cli._serve_command(args, cli_context)  # type: ignore[attr-defined]

    assert result == 0
    run_with_uvicorn.assert_called_once()
    options = run_with_uvicorn.call_args[0][0]
    assert options["reload"] is True
    assert options["workers"] is None  # reload mode ignores worker count
    mock_print.assert_called_once()


def test_serve_command_reports_missing_uvicorn(mocker, cli_context) -> None:
    mocker.patch("ai_ticket.cli._print_panel")
    mocker.patch("ai_ticket.cli._run_with_uvicorn", side_effect=ImportError("uvicorn"))

    args = _make_args()

    result = cli._serve_command(args, cli_context)  # type: ignore[attr-defined]

    assert result == 1
