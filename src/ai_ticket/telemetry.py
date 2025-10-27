"""Telemetry helpers for tracing and metrics.

This module centralises OpenTelemetry initialisation so that the rest of the
codebase can focus on emitting spans and metrics without worrying about
configuration details.  Telemetry is configured lazily – the first time a
tracer or meter is requested we provision providers and exporters based on the
current environment.
"""

from __future__ import annotations

import contextlib
import logging
import os
import threading
from contextlib import contextmanager
from enum import Enum
from typing import Final

try:  # pragma: no cover - import side effects
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.trace import SpanKind, Status, StatusCode
except ImportError:  # pragma: no cover - fallback path for tests/minimal environments
    metrics = trace = None  # type: ignore[assignment]
    OTLPSpanExporter = PrometheusMetricReader = MeterProvider = Resource = TracerProvider = BatchSpanProcessor = ConsoleSpanExporter = None  # type: ignore[assignment]
    SpanKind = None  # type: ignore[assignment]
    Status = None  # type: ignore[assignment]
    StatusCode = None  # type: ignore[assignment]
    _OTEL_AVAILABLE = False
else:
    _OTEL_AVAILABLE = True

if StatusCode is None:  # pragma: no cover - executed when OpenTelemetry unavailable
    class StatusCode(Enum):
        """Minimal stand-in for OpenTelemetry StatusCode."""

        UNSET = 0
        OK = 1
        ERROR = 2


if Status is None:  # pragma: no cover - executed when OpenTelemetry unavailable
    class Status:  # type: ignore[no-redef]
        """Fallback Status carrying a code and optional description."""

        def __init__(self, status_code: StatusCode = StatusCode.UNSET, description: str | None = None) -> None:
            self.status_code = status_code
            self.description = description


if SpanKind is None:  # pragma: no cover - executed when OpenTelemetry unavailable
    class SpanKind(Enum):  # type: ignore[no-redef]
        INTERNAL = 0
        SERVER = 1
        CLIENT = 2


_logger = logging.getLogger(__name__)

_SERVICE_NAME: Final[str] = os.getenv("OTEL_SERVICE_NAME", "ai-ticket")
_LOCK = threading.Lock()
_INITIALISED = False


def _initialise_providers() -> None:
    global _INITIALISED

    if _INITIALISED:
        return

    with _LOCK:
        if _INITIALISED:
            return

        if not _OTEL_AVAILABLE:
            _INITIALISED = True
            return

        resource = Resource.create({"service.name": _SERVICE_NAME})

        tracer_provider = TracerProvider(resource=resource)
        span_exporter = _build_span_exporter()
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)

        prom_kwargs: dict[str, object] = {}
        host = os.getenv("OTEL_PROMETHEUS_HOST")
        port = os.getenv("OTEL_PROMETHEUS_PORT")
        if host:
            prom_kwargs["addr"] = host
        if port:
            try:
                prom_kwargs["port"] = int(port)
            except ValueError:  # pragma: no cover - defensive parsing
                _logger.warning("Invalid OTEL_PROMETHEUS_PORT value '%s'; using default", port)
        try:
            metric_reader = PrometheusMetricReader(**prom_kwargs)
        except TypeError:  # pragma: no cover - compatibility fallback
            metric_reader = PrometheusMetricReader()
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)

        _INITIALISED = True


def _build_span_exporter():
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint and OTLPSpanExporter is not None:
        return OTLPSpanExporter(endpoint=endpoint)
    return ConsoleSpanExporter()


def get_tracer(name: str | None = None):
    """Return a module-specific tracer, initialising providers on first use."""

    _initialise_providers()
    if not _OTEL_AVAILABLE or trace is None:
        return _NoOpTracer()
    return trace.get_tracer(name or __name__)


def get_meter(name: str | None = None):
    """Return a module-specific meter, initialising providers on first use."""

    _initialise_providers()
    if not _OTEL_AVAILABLE or metrics is None:
        return _NoOpMeter()
    return metrics.get_meter(name or __name__)


@contextmanager
def _no_op_span():  # pragma: no cover - trivial
    yield _NoOpSpan()


class _NoOpSpan:
    def set_attribute(self, *_: object, **__: object) -> None:
        return

    def set_attributes(self, *_: object, **__: object) -> None:
        return

    def set_status(self, *_: object, **__: object) -> None:
        return

    def record_exception(self, *_: object, **__: object) -> None:
        return


class _NoOpTracer:
    def start_as_current_span(self, *_: object, **__: object) -> contextlib.AbstractContextManager[_NoOpSpan]:
        return _no_op_span()


class _NoOpInstrument:
    def add(self, *_: object, **__: object) -> None:
        return

    def record(self, *_: object, **__: object) -> None:
        return


class _NoOpMeter:
    def create_counter(self, *_: object, **__: object) -> _NoOpInstrument:
        return _NoOpInstrument()

    def create_histogram(self, *_: object, **__: object) -> _NoOpInstrument:
        return _NoOpInstrument()


__all__ = [
    "get_tracer",
    "get_meter",
    "Status",
    "StatusCode",
    "SpanKind",
]

