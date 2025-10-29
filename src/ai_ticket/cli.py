from __future__ import annotations

from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
import textwrap
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Callable, Iterable, Mapping

import requests

from ai_ticket.runtime.diagnostics import DiagnosticsReport, SimulationReport, run_diagnostics

_ACCENT_DEFAULT = "cyan"
_RESET = "\033[0m"
_COLOUR_CODES: Mapping[str, str] = {
    "cyan": "\033[38;5;45m",
    "violet": "\033[38;5;177m",
    "green": "\033[38;5;48m",
    "amber": "\033[38;5;214m",
    "red": "\033[38;5;203m",
}


@dataclass(slots=True)
class _CLIContext:
    accent: str


@dataclass(slots=True)
class _PaletteAction:
    key: str
    title: str
    description: str
    runner: Callable[["_CLIContext"], int]


def _colourise(text: str, style: str) -> str:
    colour = _COLOUR_CODES.get(style, _COLOUR_CODES.get("cyan", ""))
    reset = _RESET if colour else ""
    return f"{colour}{text}{reset}"


def _panel(title: str, body: str, style: str = "cyan") -> str:
    raw_lines: list[str] = []
    for line in body.splitlines() or [""]:
        if not line.strip():
            raw_lines.append("")
            continue
        raw_lines.extend(textwrap.wrap(line, width=72) or [""])

    content_width = max([len(title), *(len(line) for line in raw_lines)])
    border = "=" * (content_width + 4)
    title_line = f"= {title.center(content_width)} ="
    body_lines = [f"| {line.ljust(content_width)} |" for line in (raw_lines or [""])]
    panel_lines = [border, title_line, border, *body_lines, border]
    coloured = [_colourise(line, style) for line in panel_lines]
    return "\n".join(coloured)


def _print_panel(title: str, body: str, style: str = "cyan") -> None:
    print(_panel(title, body, style))


def _format_checks(report: DiagnosticsReport | SimulationReport) -> str:
    lines: list[str] = [f"Overall status: {report.status.upper()}"]
    entries: Iterable = getattr(report, "checks", getattr(report, "steps", []))
    for item in entries:
        status = item.status.upper()
        detail = item.detail
        remediation = item.remediation
        section = f"- {item.name}: {status} — {detail}"
        if remediation:
            section += f"\n  Remediation: {remediation}"
        lines.append(section)
    latency = getattr(report, "latency_seconds", None)
    if latency is not None:
        lines.append(f"Simulated processing latency: {latency:.4f}s")
    return "\n".join(lines)


def _load_flask_app():
    from ai_ticket.server import app as flask_app

    return flask_app


def _run_with_flask_reload(app, host: str, port: int) -> None:
    app.run(host=host, port=port, debug=True)


def _run_with_gunicorn(app, options: Mapping[str, object]) -> None:
    from gunicorn.app.base import BaseApplication

    class _GunicornApplication(BaseApplication):
        def __init__(self, application, opts: Mapping[str, object]) -> None:
            self.options = {**opts}
            self.application = application
            super().__init__()

        def load_config(self) -> None:  # noqa: D401
            config = {
                key: value
                for key, value in self.options.items()
                if key in self.cfg.settings and value is not None
            }
            for key, value in config.items():
                self.cfg.set(key, value)

        def load(self):  # noqa: D401
            return self.application

    _GunicornApplication(app, options).run()


def _serve_command(args: argparse.Namespace, ctx: _CLIContext) -> int:
    flask_app = _load_flask_app()

    bind = f"{args.host}:{args.port}"

    if args.reload:
        _print_panel("Server", f"Starting Flask reloader on {bind}", ctx.accent)
        try:
            _run_with_flask_reload(flask_app, args.host, args.port)
        except KeyboardInterrupt:
            _print_panel("Server", "Interrupted by user", "amber")
        return 0

    options: dict[str, object] = {
        "bind": bind,
        "workers": args.workers,
        "worker_class": args.worker_class,
        "threads": args.threads,
        "timeout": args.timeout,
        "keepalive": args.keepalive,
        "graceful_timeout": args.graceful_timeout,
        "accesslog": args.access_log,
        "errorlog": args.error_log,
    }

    summary = (
        f"Gunicorn on {bind} — {args.workers} workers, {args.worker_class}"
        + (f"/{args.threads} threads" if args.worker_class == "gthread" else "")
    )
    _print_panel("Server", summary, ctx.accent)

    try:
        _run_with_gunicorn(flask_app, options)
    except KeyboardInterrupt:
        _print_panel("Server", "Interrupted by user", "amber")
        return 0
    except ImportError as exc:
        _print_panel(
            "Server",
            "Gunicorn is required for production serving. Install it via pip.",
            "red",
        )
        _print_panel("Server", str(exc), "red")
        return 1

    return 0


def _prompt_command(args: argparse.Namespace, ctx: _CLIContext) -> int:
    url = args.server_url.rstrip("/") + "/event"
    payload = {
        "content": {
            "prompt": args.prompt_text,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
        }
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
    except requests.RequestException as exc:
        _print_panel("Prompt", f"Failed to contact service: {exc}", "red")
        return 1

    if response.status_code != requests.codes.ok:
        message = _extract_error_message(response)
        _print_panel("Prompt", f"Service returned {response.status_code}: {message}", "red")
        return 1

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        _print_panel("Prompt", f"Invalid JSON payload: {exc}", "red")
        return 1

    completion = data.get("completion") or data.get("result")
    if not isinstance(completion, str):
        _print_panel("Prompt", "Response did not include completion text.", "amber")
        return 1

    _print_panel("Completion", completion, "green")
    return 0


def _health_command(args: argparse.Namespace, ctx: _CLIContext) -> int:
    url = args.server_url.rstrip("/") + "/health"
    try:
        response = requests.get(url, timeout=10)
    except requests.RequestException as exc:
        _print_panel("Health", f"Health check failed: {exc}", "red")
        return 1

    status_style = "green" if response.status_code == requests.codes.ok else "amber"
    try:
        data = response.json()
    except json.JSONDecodeError:
        status = response.text or "unknown"
    else:
        status = str(data.get("status", "unknown"))

    body = f"HTTP {response.status_code}\nStatus: {status}"
    _print_panel("Health", body, status_style)
    return 0 if response.status_code == requests.codes.ok else 1


def _diagnostics_local(ctx: _CLIContext, overrides: Mapping[str, str] | None = None) -> DiagnosticsReport:
    report = run_diagnostics(overrides=overrides)
    _print_panel("Local diagnostics", _format_checks(report), ctx.accent)
    return report


def _dict_to_check(payload: Mapping[str, object]):
    from ai_ticket.runtime.diagnostics import DiagnosticCheck

    return DiagnosticCheck(
        name=str(payload.get("name", "unknown")),
        status=str(payload.get("status", "unknown")),
        detail=str(payload.get("detail", "")),
        remediation=(
            str(payload.get("remediation")) if payload.get("remediation") is not None else None
        ),
    )


def _diagnostics_remote(ctx: _CLIContext, server_url: str) -> tuple[int, str]:
    base_url = server_url.rstrip("/")
    overall = 0

    try:
        response = requests.get(f"{base_url}/diagnostics/self-test", timeout=20)
    except requests.RequestException as exc:
        _print_panel("Remote diagnostics", f"Failed to contact service: {exc}", "red")
        return 1, "unknown"

    if response.status_code != requests.codes.ok:
        overall = 1
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:  # pragma: no cover
        _print_panel("Remote diagnostics", f"Invalid JSON response: {exc}", "red")
        return 1, "unknown"

    report = DiagnosticsReport(
        status=str(payload.get("status", "unknown")),
        checks=[
            _dict_to_check(item)
            for item in payload.get("checks", [])
            if isinstance(item, Mapping)
        ],
    )
    _print_panel("Remote diagnostics", _format_checks(report), ctx.accent)

    try:
        sim_response = requests.post(
            f"{base_url}/diagnostics/simulate",
            json={"event": {"content": {"prompt": "Diagnostics probe"}}},
            timeout=20,
        )
    except requests.RequestException as exc:
        _print_panel("Lifecycle simulation", f"Failed to contact service: {exc}", "red")
        return 1, report.status

    if sim_response.status_code != requests.codes.ok:
        overall = 1
    try:
        sim_payload = sim_response.json()
    except json.JSONDecodeError as exc:  # pragma: no cover
        _print_panel("Lifecycle simulation", f"Invalid JSON response: {exc}", "red")
        return 1, report.status

    simulation = SimulationReport(
        status=str(sim_payload.get("status", "unknown")),
        steps=[
            _dict_to_check(item)
            for item in sim_payload.get("steps", [])
            if isinstance(item, Mapping)
        ],
        latency_seconds=(
            float(sim_payload.get("latency_seconds"))
            if sim_payload.get("latency_seconds") is not None
            else None
        ),
    )
    _print_panel("Lifecycle simulation", _format_checks(simulation), ctx.accent)
    return overall, report.status


def _diagnostics_command(args: argparse.Namespace, ctx: _CLIContext) -> int:
    exit_code = 0

    if args.local or args.local_only:
        report = _diagnostics_local(ctx)
        if report.status == "error":
            exit_code = 1

    if args.local_only:
        return exit_code

    remote_exit, status = _diagnostics_remote(ctx, args.server_url)
    exit_code = max(exit_code, remote_exit)
    if status == "error":
        exit_code = 1
    return exit_code


def _palette_actions(ctx: _CLIContext) -> list[_PaletteAction]:
    def _serve_dev() -> int:
        args = argparse.Namespace(
            host="0.0.0.0",
            port=5000,
            workers=2,
            worker_class="gthread",
            threads=4,
            timeout=30,
            keepalive=5,
            graceful_timeout=30,
            access_log="-",
            error_log="-",
            reload=True,
        )
        return _serve_command(args, ctx)

    def _health_probe() -> int:
        args = argparse.Namespace(server_url="http://localhost:5000")
        return _health_command(args, ctx)

    def _launch_init() -> int:
        args = argparse.Namespace(write_env=False, env_path=".env")
        return _init_command(args, ctx)

    def _run_diag() -> int:
        args = argparse.Namespace(server_url="http://localhost:5000", local=False, local_only=False)
        return _diagnostics_command(args, ctx)

    return [
        _PaletteAction(
            key="serve",
            title="Start development server",
            description="Run the Flask development server with reload.",
            runner=lambda _: _serve_dev(),
        ),
        _PaletteAction(
            key="health",
            title="Check service health",
            description="Call GET /health on localhost.",
            runner=lambda _: _health_probe(),
        ),
        _PaletteAction(
            key="init",
            title="Launch setup wizard",
            description="Interactively validate configuration and optionally write .env.",
            runner=lambda _: _launch_init(),
        ),
        _PaletteAction(
            key="diagnostics",
            title="Run diagnostics",
            description="Perform local and remote diagnostics against localhost.",
            runner=lambda _: _run_diag(),
        ),
    ]


def _palette_command(_args: argparse.Namespace, ctx: _CLIContext) -> int:
    actions = _palette_actions(ctx)
    lookup = {action.key: action for action in actions}
    summary = "\n".join(
        f"[{action.key}] {action.title} — {action.description}" for action in actions
    )

    while True:
        _print_panel("Command palette", summary, ctx.accent)
        query = input("Select action (or 'q' to quit): ").strip()
        if not query:
            continue
        if query.lower() in {"q", "quit", "exit"}:
            return 0

        action = lookup.get(query)
        if action is None:
            matches = difflib.get_close_matches(query, list(lookup.keys()), n=1)
            if not matches:
                _print_panel("Command palette", f"No action matches '{query}'.", "amber")
                continue
            action = lookup[matches[0]]

        result = action.runner(ctx)
        if result != 0:
            _print_panel(
                "Command palette",
                f"Action '{action.key}' exited with status {result}.",
                "amber",
            )


def _validate_path(path_str: str) -> tuple[bool, str]:
    path = Path(path_str)
    if not path.exists():
        return False, f"{path} does not exist"
    if not path.is_file():
        return False, f"{path} is not a file"
    return True, ""


def _init_command(args: argparse.Namespace, ctx: _CLIContext) -> int:
    print("\nAI Ticket interactive setup\n---------------------------")
    current = dict(os.environ)

    def _prompt(key: str, *, default: str | None = None, secret: bool = False) -> str:
        prompt = f"{key}"
        if default:
            prompt += f" [{default}]"
        prompt += ": "
        value = getpass(prompt) if secret else input(prompt)
        value = value.strip()
        if not value and default is not None:
            return default
        return value

    proposed: dict[str, str] = {}
    proposed["KOBOLDCPP_API_URL"] = _prompt(
        "KOBOLDCPP_API_URL",
        default=current.get("KOBOLDCPP_API_URL", "http://localhost:5001/api"),
    )
    token_value = _prompt(
        "AI_TICKET_AUTH_TOKEN",
        default=current.get("AI_TICKET_AUTH_TOKEN", ""),
        secret=True,
    )
    if token_value:
        proposed["AI_TICKET_AUTH_TOKEN"] = token_value
    token_file = _prompt(
        "AI_TICKET_AUTH_TOKEN_FILE",
        default=current.get("AI_TICKET_AUTH_TOKEN_FILE", ""),
    )
    if token_file:
        proposed["AI_TICKET_AUTH_TOKEN_FILE"] = token_file

    backend = _prompt(
        "RATE_LIMIT_BACKEND (memory/sqlite)",
        default=current.get("RATE_LIMIT_BACKEND", "memory"),
    ).lower()
    if backend not in {"memory", "sqlite"}:
        _print_panel("Setup", "Invalid backend; defaulting to memory.", "amber")
        backend = "memory"
    proposed["RATE_LIMIT_BACKEND"] = backend
    if backend == "sqlite":
        sqlite_path = _prompt(
            "RATE_LIMIT_SQLITE_PATH",
            default=current.get("RATE_LIMIT_SQLITE_PATH", "rate_limit.sqlite3"),
        )
        proposed["RATE_LIMIT_SQLITE_PATH"] = sqlite_path

    cert_path = _prompt(
        "AI_TICKET_TLS_CERT_PATH",
        default=current.get("AI_TICKET_TLS_CERT_PATH", ""),
    )
    key_path = _prompt(
        "AI_TICKET_TLS_KEY_PATH",
        default=current.get("AI_TICKET_TLS_KEY_PATH", ""),
    )
    if cert_path:
        proposed["AI_TICKET_TLS_CERT_PATH"] = cert_path
    if key_path:
        proposed["AI_TICKET_TLS_KEY_PATH"] = key_path

    for path_value, label in ((cert_path, "certificate"), (key_path, "key")):
        if path_value:
            valid, message = _validate_path(path_value)
            if not valid:
                _print_panel("TLS", f"{label.title()} check failed: {message}", "red")

    report = run_diagnostics(overrides=proposed)
    _print_panel("Proposed configuration", _format_checks(report), ctx.accent)

    write_env = args.write_env or input("Write values to .env file? [y/N]: ").strip().lower() == "y"
    env_path = Path(args.env_path)
    if write_env:
        if env_path.exists():
            confirm = input(f"{env_path} exists. Overwrite? [y/N]: ").strip().lower()
            if confirm != "y":
                _print_panel("Setup", "Aborted without writing .env file.", "amber")
                return 0 if report.status != "error" else 1
        with env_path.open("w", encoding="utf-8") as handle:
            for key, value in proposed.items():
                handle.write(f"{key}={value}\n")
        _print_panel("Setup", f"Configuration written to {env_path}", ctx.accent)

    return 0 if report.status != "error" else 1


def _extract_error_message(response: requests.Response) -> str:
    try:
        data = response.json()
    except json.JSONDecodeError:
        return response.text or "Unknown error"
    message = data.get("details") or data.get("message") or data.get("error")
    if message:
        return str(message)
    return json.dumps(data)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate the AI Ticket service from your terminal.")
    parser.add_argument(
        "--accent",
        default=_ACCENT_DEFAULT,
        choices=sorted(_COLOUR_CODES.keys()),
        help="Accent colour for decorated output.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Run the HTTP service with sensible defaults.")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host interface for the HTTP server.")
    serve_parser.add_argument("--port", type=int, default=5000, help="Port for the HTTP server.")
    serve_parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Number of Gunicorn worker processes to spawn.",
    )
    serve_parser.add_argument(
        "--worker-class",
        default="gthread",
        choices=["sync", "gthread", "gevent", "eventlet", "uvicorn.workers.UvicornWorker"],
        help="Gunicorn worker class. Default uses threaded workers for concurrency.",
    )
    serve_parser.add_argument(
        "--threads",
        type=int,
        default=4,
        help="Threads per worker (only used by the gthread worker class).",
    )
    serve_parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Worker timeout in seconds before Gunicorn restarts it.",
    )
    serve_parser.add_argument(
        "--keepalive",
        type=int,
        default=5,
        help="Seconds to keep idle connections open.",
    )
    serve_parser.add_argument(
        "--graceful-timeout",
        type=int,
        default=30,
        help="Seconds to allow workers to shut down gracefully.",
    )
    serve_parser.add_argument(
        "--access-log",
        default="-",
        help="Gunicorn access log destination ('-' for stdout).",
    )
    serve_parser.add_argument(
        "--error-log",
        default="-",
        help="Gunicorn error log destination ('-' for stderr).",
    )
    serve_parser.add_argument(
        "--reload",
        action="store_true",
        help="Use the Flask development server with auto-reload.",
    )
    serve_parser.set_defaults(handler=_serve_command)

    prompt_parser = subparsers.add_parser("prompt", help="Submit a prompt and display the completion.")
    prompt_parser.add_argument("prompt_text", help="Prompt text to submit to the inference backend.")
    prompt_parser.add_argument(
        "--server-url",
        default="http://localhost:5000",
        help="Base URL of the running AI Ticket service.",
    )
    prompt_parser.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature for the backend.")
    prompt_parser.add_argument("--max-tokens", type=int, default=150, help="Maximum tokens for the completion.")
    prompt_parser.set_defaults(handler=_prompt_command)

    health_parser = subparsers.add_parser("health", help="Check the health endpoint and display status.")
    health_parser.add_argument(
        "--server-url",
        default="http://localhost:5000",
        help="Base URL of the running AI Ticket service.",
    )
    health_parser.set_defaults(handler=_health_command)

    diagnostics_parser = subparsers.add_parser(
        "diagnostics",
        help="Run local and remote diagnostics to validate configuration.",
    )
    diagnostics_parser.add_argument(
        "--server-url",
        default="http://localhost:5000",
        help="Base URL of the running AI Ticket service.",
    )
    diagnostics_parser.add_argument(
        "--local",
        action="store_true",
        help="Include local diagnostics before contacting the server.",
    )
    diagnostics_parser.add_argument(
        "--local-only",
        action="store_true",
        help="Run diagnostics without contacting the remote server.",
    )
    diagnostics_parser.set_defaults(handler=_diagnostics_command)

    palette_parser = subparsers.add_parser(
        "palette",
        help="Interactive command palette for common workflows.",
    )
    palette_parser.set_defaults(handler=_palette_command)

    init_parser = subparsers.add_parser(
        "init",
        help="Interactive setup wizard for environment validation and .env generation.",
    )
    init_parser.add_argument(
        "--write-env",
        action="store_true",
        help="Write the captured values to the .env file without prompting.",
    )
    init_parser.add_argument(
        "--env-path",
        default=".env",
        help="Destination path for the generated .env file.",
    )
    init_parser.set_defaults(handler=_init_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    context = _CLIContext(accent=args.accent)
    handler: Callable[[argparse.Namespace, _CLIContext], int] = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args, context)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
