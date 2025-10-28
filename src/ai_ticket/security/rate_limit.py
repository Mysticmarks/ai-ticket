"""Rate limiting primitives supporting multi-process deployments."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Protocol


class BaseRateLimiter(Protocol):
    """Interface describing a rate limiter implementation."""

    limit: int
    window_seconds: float

    def allow(self, key: str) -> tuple[bool, float | None]:
        ...


class InMemoryRateLimiter:
    """Simple in-memory sliding window rate limiter."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, float | None]:
        now = time.monotonic()
        with self._lock:
            events = self._events.setdefault(key, [])
            cutoff = now - self.window_seconds
            while events and events[0] <= cutoff:
                events.pop(0)

            if len(events) >= self.limit:
                retry_after = max(self.window_seconds - (now - events[0]), 0.0)
                return False, retry_after

            events.append(now)
            return True, None


class SQLiteRateLimiter:
    """Rate limiter backed by SQLite for cross-process coordination."""

    def __init__(
        self,
        path: str | Path,
        limit: int,
        window_seconds: float,
        *,
        cleanup_interval: float = 60.0,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if cleanup_interval <= 0:
            raise ValueError("cleanup_interval must be positive")

        self.limit = limit
        self.window_seconds = window_seconds
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = 0.0
        self._lock = threading.Lock()

        path = Path(path)
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            path,
            check_same_thread=False,
            isolation_level=None,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._connection.execute("PRAGMA journal_mode=WAL;")
        self._connection.execute("PRAGMA synchronous=NORMAL;")
        self._initialise_schema()

    def _initialise_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rate_limit_events (
                    key TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_rate_limit_key ON rate_limit_events(key)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_rate_limit_timestamp ON rate_limit_events(timestamp)"
            )

    def allow(self, key: str) -> tuple[bool, float | None]:
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            self._maybe_cleanup(cutoff)
            cursor = self._connection.cursor()
            cursor.execute(
                "DELETE FROM rate_limit_events WHERE key = ? AND timestamp < ?",
                (key, cutoff),
            )
            cursor.execute(
                "SELECT COUNT(*), MIN(timestamp) FROM rate_limit_events WHERE key = ?",
                (key,),
            )
            count, oldest = cursor.fetchone()
            if count is None:
                count = 0

            if count >= self.limit:
                retry_after = None
                if oldest is not None:
                    retry_after = max(self.window_seconds - (now - float(oldest)), 0.0)
                cursor.close()
                return False, retry_after

            cursor.execute(
                "INSERT INTO rate_limit_events(key, timestamp) VALUES (?, ?)",
                (key, now),
            )
            cursor.close()
            return True, None

    def _maybe_cleanup(self, cutoff: float) -> None:
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        self._connection.execute(
            "DELETE FROM rate_limit_events WHERE timestamp < ?",
            (cutoff,),
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()


__all__ = ["BaseRateLimiter", "InMemoryRateLimiter", "SQLiteRateLimiter"]
