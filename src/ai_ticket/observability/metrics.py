from __future__ import annotations

import json
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, asdict
from queue import SimpleQueue
from statistics import mean
from typing import Deque, Dict, Iterable, List


@dataclass(frozen=True)
class ErrorRecord:
    id: str
    code: str
    message: str
    timestamp: float

    def as_dict(self) -> Dict[str, str | float]:
        payload = asdict(self)
        payload["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.timestamp))
        return payload


@dataclass(frozen=True)
class Outcome:
    timestamp: float
    success: bool


class MetricsStore:
    """Capture inference metrics for the dashboard."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total_requests = 0
        self._successes = 0
        self._errors = 0
        self._latencies: Deque[float] = deque(maxlen=512)
        self._event_timestamps: Deque[float] = deque()
        self._recent_outcomes: Deque[Outcome] = deque(maxlen=128)
        self._sparkline: Deque[float] = deque([0.0] * 24, maxlen=24)
        self._recent_errors: Deque[ErrorRecord] = deque(maxlen=20)
        self._subscribers: List[SimpleQueue[dict]] = []

    def record_event(
        self,
        *,
        latency_s: float,
        success: bool,
        error_code: str | None = None,
        message: str | None = None,
    ) -> None:
        now = time.time()
        with self._lock:
            self._total_requests += 1
            if success:
                self._successes += 1
            else:
                self._errors += 1
            self._latencies.append(latency_s * 1000)
            self._event_timestamps.append(now)
            self._recent_outcomes.append(Outcome(timestamp=now, success=success))

            if error_code:
                record = ErrorRecord(
                    id=str(uuid.uuid4()),
                    code=error_code,
                    message=message or "Unknown error",
                    timestamp=now,
                )
                self._recent_errors.appendleft(record)

            self._prune_events_locked(now)
            throughput_per_minute = self._calculate_throughput_locked(window=60.0, reference=now)
            self._sparkline.append(throughput_per_minute)

            snapshot = self._build_snapshot_locked(now)
            self._publish_locked(snapshot)

    def snapshot(self) -> dict:
        with self._lock:
            now = time.time()
            self._prune_events_locked(now)
            return self._build_snapshot_locked(now)

    def snapshot_json(self) -> str:
        return json.dumps(self.snapshot())

    def subscribe(self) -> SimpleQueue[dict]:
        queue: SimpleQueue[dict] = SimpleQueue()
        with self._lock:
            self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: SimpleQueue[dict]) -> None:
        with self._lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    def _publish_locked(self, snapshot: dict) -> None:
        for queue in list(self._subscribers):
            queue.put(snapshot)

    def _prune_events_locked(self, reference_time: float) -> None:
        cutoff = reference_time - 15 * 60
        while self._event_timestamps and self._event_timestamps[0] < cutoff:
            self._event_timestamps.popleft()
        while self._recent_outcomes and self._recent_outcomes[0].timestamp < cutoff:
            self._recent_outcomes.popleft()
        while self._recent_errors and self._recent_errors[-1].timestamp < cutoff:
            self._recent_errors.pop()

    def _calculate_throughput_locked(self, *, window: float, reference: float) -> float:
        relevant_events = [ts for ts in self._event_timestamps if reference - ts <= window]
        if window <= 0:
            return 0.0
        return len(relevant_events) / (window / 60.0)

    def _percentile(self, data: Iterable[float], percentile: float) -> float:
        values = sorted(data)
        if not values:
            return 0.0
        if len(values) == 1:
            return values[0]
        rank = percentile * (len(values) - 1)
        lower_index = int(rank)
        upper_index = min(lower_index + 1, len(values) - 1)
        weight = rank - lower_index
        return values[lower_index] * (1 - weight) + values[upper_index] * weight

    def _build_status_panels_locked(self) -> List[dict]:
        recent_events = list(self._recent_outcomes)[-20:]
        if recent_events:
            failure_ratio = 1 - (sum(1 for outcome in recent_events if outcome.success) / len(recent_events))
        else:
            failure_ratio = 0.0

        backend_state = "online"
        if failure_ratio > 0.5:
            backend_state = "offline"
        elif failure_ratio > 0.25:
            backend_state = "degraded"

        avg_latency = mean(self._latencies) if self._latencies else 0.0
        latency_state = "online"
        if avg_latency > 2500:
            latency_state = "offline"
        elif avg_latency > 1200:
            latency_state = "degraded"

        throughput_now = self._sparkline[-1] if self._sparkline else 0.0
        throughput_state = "online"
        if throughput_now < 5 and self._total_requests > 20:
            throughput_state = "degraded"

        return [
            {
                "id": "backend",
                "label": "Inference Backend",
                "state": backend_state,
                "message": f"Failure ratio (last 20 events): {failure_ratio:.0%}",
            },
            {
                "id": "latency",
                "label": "Latency Watch",
                "state": latency_state,
                "message": f"Average latency: {avg_latency:.0f} ms",
            },
            {
                "id": "throughput",
                "label": "Pipeline Throughput",
                "state": throughput_state,
                "message": f"Requests per minute: {throughput_now:.1f}",
            },
        ]

    def _build_snapshot_locked(self, reference_time: float) -> dict:
        per_second = self._calculate_throughput_locked(window=1.0, reference=reference_time) * (1 / 60)
        per_minute = self._calculate_throughput_locked(window=60.0, reference=reference_time)

        latency_values = list(self._latencies)

        snapshot = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(reference_time)),
            "totals": {
                "requests": self._total_requests,
                "successes": self._successes,
                "errors": self._errors,
            },
            "latency": {
                "average": mean(latency_values) if latency_values else 0.0,
                "p50": self._percentile(latency_values, 0.5),
                "p95": self._percentile(latency_values, 0.95),
            },
            "throughput": {
                "perSecond": per_second,
                "perMinute": per_minute,
            },
            "sparkline": self._normalise_sparkline(list(self._sparkline)),
            "statusPanels": self._build_status_panels_locked(),
            "recentErrors": [record.as_dict() for record in list(self._recent_errors)],
        }
        return snapshot

    def _normalise_sparkline(self, values: List[float]) -> List[float]:
        if not values:
            return []
        max_value = max(values)
        if max_value == 0:
            return [0.1 for _ in values]
        return [max(value / max_value, 0.1) for value in values]


metrics_store = MetricsStore()

__all__ = ["metrics_store", "MetricsStore"]
