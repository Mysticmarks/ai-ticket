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


def _serve_command(args: argparse.Namespace, ctx: _CLIContext) -> int:
    from ai_ticket.server import app as flask_app

    _print_panel("Server", f"Starting on {args.host}:{args.port}", ctx.accent)
    try:
        flask_app.run(host=args.host, port=args.port, debug=args.reload)
    except KeyboardInterrupt:
        _print_panel("Server", "Interrupted by user", "amber")
        return 0
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
    serve_parser.add_argument("--reload", action="store_true", help="Enable Flask debug auto-reload (development only).")
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
