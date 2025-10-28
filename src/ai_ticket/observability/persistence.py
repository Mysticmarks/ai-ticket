"""Persistence backends for the dashboard metrics store."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Totals:
    requests: int
    successes: int
    errors: int


@dataclass(frozen=True)
class PersistedEvent:
    timestamp: float
    latency_ms: float
    success: bool
    error_code: str | None
    message: str | None


class MetricsPersistence(Protocol):
    """Protocol describing the persistence hooks used by ``MetricsStore``."""

    def load_state(
        self,
        *,
        reference_time: float,
        retention_seconds: float,
    ) -> tuple[Totals, Sequence[PersistedEvent]]:
        ...

    def persist_event(
        self,
        *,
        timestamp: float,
        latency_ms: float,
        success: bool,
        error_code: str | None,
        message: str | None,
    ) -> None:
        ...

    def prune(self, *, cutoff: float) -> None:
        ...


class SQLiteMetricsPersistence:
    """SQLite-backed persistence provider for dashboard metrics."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        if not self._path.parent.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(
            self._path,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.execute("PRAGMA journal_mode=WAL;")
        self._connection.execute("PRAGMA synchronous=NORMAL;")
        self._initialise_schema()

    def _initialise_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS metrics_totals (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    requests INTEGER NOT NULL,
                    successes INTEGER NOT NULL,
                    errors INTEGER NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                INSERT OR IGNORE INTO metrics_totals(id, requests, successes, errors)
                VALUES (1, 0, 0, 0)
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS metrics_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    latency_ms REAL NOT NULL,
                    success INTEGER NOT NULL,
                    error_code TEXT,
                    message TEXT
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_metrics_events_timestamp ON metrics_events(timestamp)"
            )

    def load_state(
        self,
        *,
        reference_time: float,
        retention_seconds: float,
    ) -> tuple[Totals, Sequence[PersistedEvent]]:
        cutoff = reference_time - retention_seconds
        cursor = self._connection.cursor()
        cursor.execute("SELECT requests, successes, errors FROM metrics_totals WHERE id = 1")
        row = cursor.fetchone()
        if row is None:
            totals = Totals(0, 0, 0)
        else:
            totals = Totals(int(row[0]), int(row[1]), int(row[2]))

        cursor.execute(
            """
            SELECT timestamp, latency_ms, success, error_code, message
            FROM metrics_events
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (cutoff,),
        )
        events = [
            PersistedEvent(
                timestamp=float(item[0]),
                latency_ms=float(item[1]),
                success=bool(item[2]),
                error_code=item[3],
                message=item[4],
            )
            for item in cursor.fetchall()
        ]
        cursor.close()
        return totals, events

    def persist_event(
        self,
        *,
        timestamp: float,
        latency_ms: float,
        success: bool,
        error_code: str | None,
        message: str | None,
    ) -> None:
        with self._lock:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO metrics_events(timestamp, latency_ms, success, error_code, message)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (timestamp, latency_ms, int(success), error_code, message),
                )
                self._connection.execute(
                    """
                    UPDATE metrics_totals
                    SET requests = requests + 1,
                        successes = successes + ?,
                        errors = errors + ?
                    WHERE id = 1
                    """,
                    (1 if success else 0, 0 if success else 1),
                )

    def prune(self, *, cutoff: float) -> None:
        with self._lock:
            with self._connection:
                self._connection.execute(
                    "DELETE FROM metrics_events WHERE timestamp < ?",
                    (cutoff,),
                )

    def close(self) -> None:
        with self._lock:
            self._connection.close()


__all__ = [
    "MetricsPersistence",
    "PersistedEvent",
    "SQLiteMetricsPersistence",
    "Totals",
]
