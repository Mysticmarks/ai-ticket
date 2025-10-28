from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from statistics import mean

import pytest

from ai_ticket._compat import httpx
from ai_ticket.events.inference import KoboldCompletionResult
from ai_ticket.observability.metrics import MetricsStore
from ai_ticket.server import app as flask_app


@pytest.mark.performance
def test_event_endpoint_meets_latency_and_throughput(monkeypatch) -> None:
    request_count = 24
    max_workers = 6

    metrics_probe = MetricsStore()
    monkeypatch.setattr("ai_ticket.server.metrics_store", metrics_probe)

    def _fake_backend(prompt: str) -> KoboldCompletionResult:
        time.sleep(0.005)
        return KoboldCompletionResult(completion="stubbed")

    monkeypatch.setattr(
        "ai_ticket.events.inference.get_kobold_completion",
        _fake_backend,
    )

    payload = {"content": {"prompt": "Load test prompt"}}

    def _exercise(_: int) -> float:
        transport = httpx.WSGITransport(app=flask_app)
        with httpx.Client(transport=transport, base_url="http://testserver") as client:
            start = time.perf_counter()
            response = client.post("/event", json=payload)
            elapsed = time.perf_counter() - start
            assert response.status_code == 200
            assert response.json()["completion"] == "stubbed"
            return elapsed

    durations: list[float] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for duration in executor.map(_exercise, range(request_count)):
            durations.append(duration)

    snapshot = metrics_probe.snapshot()

    assert snapshot["totals"]["requests"] == request_count
    assert snapshot["latency"]["p95"] < 250
    assert snapshot["throughput"]["perSecond"] >= 1.0

    observed_average = mean(durations) * 1000
    assert observed_average < 200
