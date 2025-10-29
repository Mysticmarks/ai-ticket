from __future__ import annotations

import os
from pathlib import Path

import pytest

from ai_ticket.runtime import diagnostics
from ai_ticket.security import InMemoryRateLimiter, TokenManager


@pytest.fixture(autouse=True)
def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "KOBOLDCPP_API_URL",
        "AI_TICKET_AUTH_TOKEN",
        "AI_TICKET_AUTH_TOKEN_FILE",
        "AI_TICKET_TLS_CERT_PATH",
        "AI_TICKET_TLS_KEY_PATH",
        "RATE_LIMIT_BACKEND",
        "RATE_LIMIT_SQLITE_PATH",
        "AI_TICKET_METRICS_DB",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_run_diagnostics_reports_tls_warning(tmp_path: Path) -> None:
    report = diagnostics.run_diagnostics(
        overrides={"KOBOLDCPP_API_URL": "http://localhost:5001/api"}
    )
    statuses = {check.name: check.status for check in report.checks}
    assert statuses["kobold_endpoint"] == "warning"
    assert statuses["tls_assets"] == "warning"


def test_run_diagnostics_with_tls_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("cert")
    key.write_text("key")
    overrides = {
        "KOBOLDCPP_API_URL": "https://api.example.com",
        "AI_TICKET_TLS_CERT_PATH": str(cert),
        "AI_TICKET_TLS_KEY_PATH": str(key),
        "AI_TICKET_AUTH_TOKEN": "secret-token",
    }
    report = diagnostics.run_diagnostics(overrides=overrides)
    statuses = {check.name: check.status for check in report.checks}
    assert statuses["kobold_endpoint"] == "ok"
    assert statuses["tls_assets"] == "ok"
    assert statuses["authentication"] == "ok"


def test_simulate_request_lifecycle_success(monkeypatch: pytest.MonkeyPatch) -> None:
    token_manager = TokenManager(reload_interval=1.0)
    token_manager.update_tokens(["token"])
    limiter = InMemoryRateLimiter(limit=5, window_seconds=60)

    report = diagnostics.simulate_request_lifecycle(
        token_manager=token_manager,
        rate_limiter=limiter,
        event_payload={"content": {"prompt": "hello"}},
    )

    statuses = {step.name: step.status for step in report.steps}
    assert report.status == "ok"
    assert statuses["rate_limiter"] == "ok"
    assert statuses["authentication"] == "ok"
    assert statuses["payload_validation"] == "ok"


def test_simulate_request_lifecycle_with_invalid_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = InMemoryRateLimiter(limit=1, window_seconds=60)
    token_manager = TokenManager(reload_interval=1.0)

    report = diagnostics.simulate_request_lifecycle(
        token_manager=token_manager,
        rate_limiter=limiter,
        event_payload={},
    )

    statuses = {step.name: step.status for step in report.steps}
    assert report.status == "error"
    assert statuses["payload_validation"] == "error"
