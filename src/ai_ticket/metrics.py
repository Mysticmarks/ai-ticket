from __future__ import annotations

import importlib.util
import math
import threading
from typing import Dict, Iterable, Tuple

if importlib.util.find_spec("prometheus_client") is not None:  # pragma: no cover - real library path
    from prometheus_client import (  # type: ignore
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
else:  # pragma: no cover - exercised in CI without prometheus_client
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    _REGISTRY: list["_Metric"] = []

    class _Metric:
        def __init__(self, name: str, documentation: str, labelnames: Iterable[str], namespace: str | None) -> None:
            self.name = f"{namespace}_{name}" if namespace else name
            self.documentation = documentation
            self.labelnames = tuple(labelnames)
            self._lock = threading.Lock()
            self._children: Dict[Tuple[str, ...], "_ChildBase"] = {}
            _REGISTRY.append(self)

        def labels(self, *labelvalues: str, **labelkwargs: str) -> "_ChildBase":
            if labelkwargs:
                if labelvalues:
                    raise ValueError("Specify labels using positional OR keyword arguments, not both.")
                labelvalues = tuple(str(labelkwargs[name]) for name in self.labelnames)  # type: ignore[assignment]
            else:
                if len(labelvalues) != len(self.labelnames):
                    raise ValueError("Incorrect number of labels provided.")
            key = tuple(str(value) for value in labelvalues)
            with self._lock:
                child = self._children.get(key)
                if child is None:
                    child = self._child_class(self, key)
                    self._children[key] = child
            return child

        def _format_labels(self, labelvalues: Tuple[str, ...], extra: dict[str, str] | None = None) -> str:
            if not self.labelnames and not extra:
                return ""
            labels = {name: value for name, value in zip(self.labelnames, labelvalues)}
            if extra:
                labels.update(extra)
            encoded = ",".join(f'{key}="{value}"' for key, value in labels.items())
            return f"{{{encoded}}}" if encoded else ""

        def render(self) -> list[str]:
            raise NotImplementedError

    class _ChildBase:
        def __init__(self, metric: _Metric, labelvalues: Tuple[str, ...]) -> None:
            self.metric = metric
            self.labelvalues = labelvalues

    class Counter(_Metric):
        def __init__(
            self,
            name: str,
            documentation: str,
            labelnames: Iterable[str] | None = None,
            namespace: str | None = None,
        ) -> None:
            super().__init__(name, documentation, labelnames or (), namespace)

        class _Child(_ChildBase):
            def __init__(self, metric: _Metric, labelvalues: Tuple[str, ...]) -> None:
                super().__init__(metric, labelvalues)
                self.value = 0.0

            def inc(self, amount: float = 1.0) -> None:
                if amount < 0:
                    raise ValueError("Counters can only be increased.")
                self.value += amount

        _child_class = _Child

        def inc(self, amount: float = 1.0) -> None:
            if self.labelnames:
                raise ValueError("Must supply labels to increment a labelled counter.")
            child = self.labels(*(()))
            child.inc(amount)

        def render(self) -> list[str]:
            lines = [f"# HELP {self.name} {self.documentation}", f"# TYPE {self.name} counter"]
            for labels, child in self._children.items():
                label_str = self._format_labels(labels)
                lines.append(f"{self.name}{label_str} {child.value}")
            return lines

    class Gauge(_Metric):
        def __init__(
            self,
            name: str,
            documentation: str,
            labelnames: Iterable[str] | None = None,
            namespace: str | None = None,
        ) -> None:
            super().__init__(name, documentation, labelnames or (), namespace)

        class _Child(_ChildBase):
            def __init__(self, metric: _Metric, labelvalues: Tuple[str, ...]) -> None:
                super().__init__(metric, labelvalues)
                self.value = 0.0
                self._lock = threading.Lock()

            def inc(self, amount: float = 1.0) -> None:
                with self._lock:
                    self.value += amount

            def dec(self, amount: float = 1.0) -> None:
                with self._lock:
                    self.value -= amount

            def set(self, value: float) -> None:
                with self._lock:
                    self.value = value

        _child_class = _Child

        def _ensure_unlabelled(self) -> _Child:
            if self.labelnames:
                raise ValueError("Must supply labels when mutating a labelled gauge.")
            return self.labels(*(()))  # type: ignore[return-value]

        def inc(self, amount: float = 1.0) -> None:
            self._ensure_unlabelled().inc(amount)

        def dec(self, amount: float = 1.0) -> None:
            self._ensure_unlabelled().dec(amount)

        def set(self, value: float) -> None:
            self._ensure_unlabelled().set(value)

        def render(self) -> list[str]:
            lines = [f"# HELP {self.name} {self.documentation}", f"# TYPE {self.name} gauge"]
            for labels, child in self._children.items():
                label_str = self._format_labels(labels)
                lines.append(f"{self.name}{label_str} {child.value}")
            return lines

    class Histogram(_Metric):
        DEFAULT_BUCKETS = (
            0.005,
            0.01,
            0.025,
            0.05,
            0.075,
            0.1,
            0.25,
            0.5,
            0.75,
            1.0,
            2.5,
            5.0,
            7.5,
            10.0,
        )

        class _Child(_ChildBase):
            def __init__(self, metric: "Histogram", labelvalues: Tuple[str, ...]) -> None:
                super().__init__(metric, labelvalues)
                bucket_count = len(metric._bucket_bounds)
                self.bucket_counts = [0 for _ in range(bucket_count)]
                self.count = 0
                self.sum = 0.0

            def observe(self, amount: float) -> None:
                self.count += 1
                self.sum += amount
                for index, upper in enumerate(self.metric._bucket_bounds[:-1]):
                    if amount <= upper:
                        self.bucket_counts[index] += 1
                # +Inf bucket mirrors total count
                self.bucket_counts[-1] = self.count

        _child_class = _Child

        def __init__(
            self,
            name: str,
            documentation: str,
            labelnames: Iterable[str],
            namespace: str | None = None,
            buckets: Iterable[float] | None = None,
        ) -> None:
            self._bucket_bounds = tuple(sorted(buckets or self.DEFAULT_BUCKETS)) + (math.inf,)
            super().__init__(name, documentation, labelnames, namespace)

        def observe(self, amount: float) -> None:
            if self.labelnames:
                raise ValueError("Must supply labels when observing a labelled histogram.")
            child = self.labels(*(()))  # type: ignore[return-value]
            child.observe(amount)

        def render(self) -> list[str]:
            lines = [f"# HELP {self.name} {self.documentation}", f"# TYPE {self.name} histogram"]
            for labels, child in self._children.items():
                for index, upper in enumerate(self._bucket_bounds):
                    le_value = "+Inf" if math.isinf(upper) else f"{upper:g}"
                    bucket_labels = self._format_labels(labels, {"le": le_value})
                    lines.append(f"{self.name}_bucket{bucket_labels} {child.bucket_counts[index]}")
                sum_labels = self._format_labels(labels)
                lines.append(f"{self.name}_sum{sum_labels} {child.sum}")
                lines.append(f"{self.name}_count{sum_labels} {child.count}")
            return lines

    def generate_latest() -> bytes:
        lines: list[str] = []
        for metric in _REGISTRY:
            lines.extend(metric.render())
        return ("\n".join(lines) + "\n").encode("utf-8")
