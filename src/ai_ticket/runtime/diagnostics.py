"""Self-diagnostics and configuration validation helpers."""

from __future__ import annotations

import contextlib
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Sequence

from ai_ticket.events.common import validate_inference_event
from ai_ticket.events.prompt_extraction import extract_prompt
from ai_ticket.events.validation import ValidationError
from ai_ticket.security import BaseRateLimiter, TokenManager


@dataclass(frozen=True)
class DiagnosticCheck:
    """Represents the outcome of an individual diagnostic step."""

    name: str
    status: str
    detail: str
    remediation: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DiagnosticsReport:
    """Aggregated configuration diagnostics."""

    status: str
    checks: Sequence[DiagnosticCheck]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "checks": [check.to_dict() for check in self.checks],
        }


@dataclass(frozen=True)
class SimulationReport:
    """Represents a simulated request lifecycle."""

    status: str
    steps: Sequence[DiagnosticCheck]
    latency_seconds: float | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status,
            "steps": [step.to_dict() for step in self.steps],
        }
        if self.latency_seconds is not None:
            payload["latency_seconds"] = self.latency_seconds
        return payload


_STATUS_ORDER = {"ok": 0, "warning": 1, "error": 2}
_TLS_CERT_ENV = "AI_TICKET_TLS_CERT_PATH"
_TLS_KEY_ENV = "AI_TICKET_TLS_KEY_PATH"


@contextlib.contextmanager
def _temporary_env(overrides: Mapping[str, str] | None) -> Iterable[None]:
    if not overrides:
        yield
        return

    original: MutableMapping[str, str | None] = {}
    for key, value in overrides.items():
        original[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, previous in original.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


def _combine_status(current: str, new: str) -> str:
    if _STATUS_ORDER.get(new, 0) > _STATUS_ORDER.get(current, 0):
        return new
    return current


def _check_kobold_endpoint(env: Mapping[str, str]) -> DiagnosticCheck:
    url = env.get("KOBOLDCPP_API_URL") or ""
    if not url:
        return DiagnosticCheck(
            name="kobold_endpoint",
            status="warning",
            detail="KOBOLDCPP_API_URL is not set; defaulting to http://localhost:5001/api.",
            remediation="Set KOBOLDCPP_API_URL to a reachable endpoint for non-local deployments.",
        )
    if url.startswith("http://localhost") or "127.0.0.1" in url:
        return DiagnosticCheck(
            name="kobold_endpoint",
            status="warning",
            detail=(
                "KOBOLDCPP_API_URL targets a localhost endpoint. Ensure production deployments"
                " point to a routable service."
            ),
        )
    return DiagnosticCheck(
        name="kobold_endpoint",
        status="ok",
        detail=f"Using inference endpoint {url}",
    )


def _check_authentication(env: Mapping[str, str]) -> DiagnosticCheck:
    tokens = env.get("AI_TICKET_AUTH_TOKEN", "").strip()
    token_file = env.get("AI_TICKET_AUTH_TOKEN_FILE", "").strip()

    if not tokens and not token_file:
        return DiagnosticCheck(
            name="authentication",
            status="warning",
            detail="No API tokens configured; /event will accept anonymous traffic.",
            remediation="Set AI_TICKET_AUTH_TOKEN or AI_TICKET_AUTH_TOKEN_FILE to secure the API.",
        )

    manager = TokenManager(reload_interval=1.0)
    if manager.has_tokens():
        return DiagnosticCheck(
            name="authentication",
            status="ok",
            detail=f"Loaded {len(manager.tokens)} API token(s).",
        )

    return DiagnosticCheck(
        name="authentication",
        status="error",
        detail="Token sources were configured but no tokens could be loaded.",
        remediation="Verify AI_TICKET_AUTH_TOKEN and AI_TICKET_AUTH_TOKEN_FILE paths.",
    )


def _check_rate_limiter(env: Mapping[str, str]) -> DiagnosticCheck:
    backend = (env.get("RATE_LIMIT_BACKEND") or "memory").lower()
    try:
        requests_limit = int(env.get("RATE_LIMIT_REQUESTS", "120"))
        window_seconds = float(env.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
    except ValueError:
        return DiagnosticCheck(
            name="rate_limiter",
            status="error",
            detail="Rate limit configuration is invalid (non-numeric values).",
            remediation="Use integers for RATE_LIMIT_REQUESTS and numeric seconds for RATE_LIMIT_WINDOW_SECONDS.",
        )

    if requests_limit <= 0 or window_seconds <= 0:
        return DiagnosticCheck(
            name="rate_limiter",
            status="warning",
            detail="Rate limiting is disabled; set positive limits to prevent abuse.",
        )

    if backend not in {"memory", "sqlite"}:
        return DiagnosticCheck(
            name="rate_limiter",
            status="error",
            detail=f"Unsupported rate limit backend '{backend}'.",
            remediation="Choose either 'memory' or 'sqlite'.",
        )

    if backend == "sqlite":
        path = Path(env.get("RATE_LIMIT_SQLITE_PATH", "rate_limit.sqlite3"))
        try:
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
                path.unlink()  # leave path untouched but confirm write access
        except OSError as exc:
            return DiagnosticCheck(
                name="rate_limiter",
                status="error",
                detail=f"SQLite rate limiter path is not writable: {exc}",
                remediation="Adjust RATE_LIMIT_SQLITE_PATH or file permissions.",
            )

    return DiagnosticCheck(
        name="rate_limiter",
        status="ok",
        detail=f"Rate limiter configured with backend '{backend}'.",
    )


def _check_metrics_storage(env: Mapping[str, str]) -> DiagnosticCheck:
    db_path = env.get("AI_TICKET_METRICS_DB", "").strip()
    if not db_path:
        return DiagnosticCheck(
            name="metrics_storage",
            status="ok",
            detail="In-memory metrics snapshot in use.",
        )

    path = Path(db_path)
    try:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            path.unlink()
    except OSError as exc:
        return DiagnosticCheck(
            name="metrics_storage",
            status="error",
            detail=f"Metrics database path is not writable: {exc}",
            remediation="Update AI_TICKET_METRICS_DB or adjust filesystem permissions.",
        )

    return DiagnosticCheck(
        name="metrics_storage",
        status="ok",
        detail=f"Metrics snapshots will persist to {path}",
    )


def _check_tls_assets(env: Mapping[str, str]) -> DiagnosticCheck:
    cert_path = env.get(_TLS_CERT_ENV, "").strip()
    key_path = env.get(_TLS_KEY_ENV, "").strip()

    if not cert_path and not key_path:
        return DiagnosticCheck(
            name="tls_assets",
            status="warning",
            detail="TLS certificate and key are not configured; traffic will use HTTP.",
            remediation=f"Set {_TLS_CERT_ENV} and {_TLS_KEY_ENV} to enable TLS termination.",
        )

    if not cert_path or not key_path:
        return DiagnosticCheck(
            name="tls_assets",
            status="error",
            detail="Both certificate and key paths must be provided for TLS.",
            remediation=f"Set both {_TLS_CERT_ENV} and {_TLS_KEY_ENV} environment variables.",
        )

    cert = Path(cert_path)
    key = Path(key_path)
    missing: list[str] = []
    if not cert.exists():
        missing.append(cert_path)
    if not key.exists():
        missing.append(key_path)
    if missing:
        return DiagnosticCheck(
            name="tls_assets",
            status="error",
            detail=f"TLS asset(s) missing: {', '.join(missing)}",
            remediation="Verify the certificate/key paths and filesystem permissions.",
        )

    return DiagnosticCheck(
        name="tls_assets",
        status="ok",
        detail="TLS certificate and key are present.",
    )


def run_diagnostics(*, overrides: Mapping[str, str] | None = None) -> DiagnosticsReport:
    """Evaluate configuration and runtime dependencies.

    Parameters
    ----------
    overrides:
        Optional environment overrides used during validation (without mutating
        the real process environment).
    """

    with _temporary_env(overrides):
        env = dict(os.environ)
        checks = [
            _check_kobold_endpoint(env),
            _check_authentication(env),
            _check_rate_limiter(env),
            _check_tls_assets(env),
            _check_metrics_storage(env),
        ]

    status = "ok"
    for check in checks:
        status = _combine_status(status, check.status)

    return DiagnosticsReport(status=status, checks=checks)


def simulate_request_lifecycle(
    *,
    token_manager: TokenManager | None,
    rate_limiter: BaseRateLimiter | None,
    event_payload: Mapping[str, object] | None = None,
) -> SimulationReport:
    """Simulate processing an inference request without contacting the backend."""

    checks: list[DiagnosticCheck] = []
    status = "ok"
    start_time = time.perf_counter()

    if rate_limiter is not None:
        allowed, retry_after = rate_limiter.allow("diagnostics::probe")
        if allowed:
            checks.append(
                DiagnosticCheck(
                    name="rate_limiter",
                    status="ok",
                    detail="Rate limiter accepted diagnostic probe.",
                )
            )
        else:
            status = "error"
            detail = "Rate limiter rejected diagnostic probe."
            if retry_after is not None:
                detail += f" Retry after {retry_after:.1f}s."
            checks.append(
                DiagnosticCheck(
                    name="rate_limiter",
                    status="error",
                    detail=detail,
                    remediation="Increase RATE_LIMIT_REQUESTS or inspect active traffic before enabling diagnostics.",
                )
            )
    else:
        status = _combine_status(status, "warning")
        checks.append(
            DiagnosticCheck(
                name="rate_limiter",
                status="warning",
                detail="Rate limiter is disabled; diagnostics will not enforce quotas.",
            )
        )

    if token_manager is not None and token_manager.has_tokens():
        checks.append(
            DiagnosticCheck(
                name="authentication",
                status="ok",
                detail=f"Authentication enabled with {len(token_manager.tokens)} token(s).",
            )
        )
    elif token_manager is not None:
        status = _combine_status(status, "warning")
        checks.append(
            DiagnosticCheck(
                name="authentication",
                status="warning",
                detail="Authentication is configured but no tokens are active.",
                remediation="Reload tokens or update AI_TICKET_AUTH_TOKEN[_FILE].",
            )
        )
    else:
        status = _combine_status(status, "warning")
        checks.append(
            DiagnosticCheck(
                name="authentication",
                status="warning",
                detail="Authentication manager unavailable; diagnostics cannot validate credentials.",
            )
        )

    payload = event_payload if event_payload is not None else {"content": {"prompt": "Diagnostics handshake"}}
    try:
        content_key = validate_inference_event(payload)
        extraction = extract_prompt(payload[content_key])
    except ValidationError as exc:
        status = "error"
        checks.append(
            DiagnosticCheck(
                name="payload_validation",
                status="error",
                detail=f"Sample payload failed validation: {exc.code}",
                remediation="Ensure diagnostic payload matches the /event contract.",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                name="payload_validation",
                status="ok",
                detail=f"Sample prompt extracted ({len(extraction.prompt)} characters).",
            )
        )

    elapsed = time.perf_counter() - start_time
    return SimulationReport(status=status, steps=checks, latency_seconds=elapsed)


__all__ = [
    "DiagnosticCheck",
    "DiagnosticsReport",
    "SimulationReport",
    "run_diagnostics",
    "simulate_request_lifecycle",
]
