"""Prometheus helper utilities with a graceful fallback when the client is unavailable."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple
import threading

try:  # pragma: no cover - used when prometheus_client is installed
    from prometheus_client import CONTENT_TYPE_LATEST  # type: ignore
    from prometheus_client import Counter  # type: ignore
    from prometheus_client import Histogram  # type: ignore
    from prometheus_client import generate_latest  # type: ignore
except ImportError:  # pragma: no cover - fallback covered by unit tests
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    _REGISTRY: list["_Metric"] = []
    _REGISTRY_LOCK = threading.Lock()

    def _register(metric: "_Metric") -> None:
        with _REGISTRY_LOCK:
            _REGISTRY.append(metric)

    class _Metric:
        def __init__(self, name: str, documentation: str, labelnames: Iterable[str] | None):
            self.name = name
            self.documentation = documentation
            self.labelnames = tuple(labelnames or ())
            self._lock = threading.Lock()
            _register(self)

        def labels(self, *values: str):
            if len(values) != len(self.labelnames):
                raise ValueError("Incorrect number of labels passed to metric")
            return self._child(values)

        def _child(self, values: Tuple[str, ...]):
            raise NotImplementedError

    class Counter(_Metric):
        def __init__(self, name: str, documentation: str, labelnames: Iterable[str] | None = None):
            super().__init__(name, documentation, labelnames)
            self._samples: Dict[Tuple[str, ...], float] = {}

        def _child(self, values: Tuple[str, ...]):
            return _CounterChild(self, values)

        def _inc(self, values: Tuple[str, ...], amount: float = 1.0) -> None:
            with self._lock:
                self._samples[values] = self._samples.get(values, 0.0) + amount

        def _collect(self) -> Dict[Tuple[str, ...], float]:
            with self._lock:
                return dict(self._samples)

    class _CounterChild:
        def __init__(self, metric: Counter, values: Tuple[str, ...]):
            self._metric = metric
            self._values = values

        def inc(self, amount: float = 1.0) -> None:
            self._metric._inc(self._values, amount)

    class Histogram(_Metric):
        def __init__(self, name: str, documentation: str, labelnames: Iterable[str] | None = None):
            super().__init__(name, documentation, labelnames)
            self._samples: Dict[Tuple[str, ...], Tuple[int, float]] = {}

        def _child(self, values: Tuple[str, ...]):
            return _HistogramChild(self, values)

        def _observe(self, values: Tuple[str, ...], amount: float) -> None:
            with self._lock:
                count, total = self._samples.get(values, (0, 0.0))
                self._samples[values] = (count + 1, total + amount)

        def _collect(self) -> Dict[Tuple[str, ...], Tuple[int, float]]:
            with self._lock:
                return dict(self._samples)

    class _HistogramChild:
        def __init__(self, metric: Histogram, values: Tuple[str, ...]):
            self._metric = metric
            self._values = values

        def observe(self, amount: float) -> None:
            self._metric._observe(self._values, amount)

    def _format_labels(names: Iterable[str], values: Iterable[str]) -> str:
        pairs = [f'{name}="{value}"' for name, value in zip(names, values)]
        if not pairs:
            return ""
        return "{" + ",".join(pairs) + "}"

    def generate_latest() -> bytes:
        lines: list[str] = []
        with _REGISTRY_LOCK:
            registry_snapshot = list(_REGISTRY)
        for metric in registry_snapshot:
            lines.append(f"# HELP {metric.name} {metric.documentation}")
            if isinstance(metric, Counter):
                lines.append(f"# TYPE {metric.name} counter")
                for labels, value in metric._collect().items():
                    label_string = _format_labels(metric.labelnames, labels)
                    lines.append(f"{metric.name}{label_string} {value}")
            elif isinstance(metric, Histogram):
                lines.append(f"# TYPE {metric.name} histogram")
                for labels, (count, total) in metric._collect().items():
                    base_labels = _format_labels(metric.labelnames, labels)
                    bucket_labels = _format_labels(metric.labelnames + ("le",), labels + ("+Inf",))
                    lines.append(f"{metric.name}_bucket{bucket_labels} {count}")
                    lines.append(f"{metric.name}_count{base_labels} {count}")
                    lines.append(f"{metric.name}_sum{base_labels} {total}")
        return ("\n".join(lines) + "\n").encode("utf-8")

    __all__ = ["Counter", "Histogram", "generate_latest", "CONTENT_TYPE_LATEST"]

else:  # pragma: no cover
    __all__ = ["Counter", "Histogram", "generate_latest", "CONTENT_TYPE_LATEST"]
