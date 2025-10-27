from __future__ import annotations

import argparse
import json
import sys
import textwrap
from dataclasses import dataclass
from typing import Callable, Mapping

import requests

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
