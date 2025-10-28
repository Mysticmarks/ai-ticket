"""Authentication helpers with reloadable token sources."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Iterable, Set


class TokenManager:
    """Centralises API token loading with automatic refreshes.

    Tokens can be provided via the ``AI_TICKET_AUTH_TOKEN`` environment variable
    (comma separated) and/or via a file pointed to by
    ``AI_TICKET_AUTH_TOKEN_FILE``.  The manager re-reads its sources whenever a
    configurable interval has elapsed or the backing file changes on disk.  This
    keeps multi-process deployments in sync without requiring a service restart
    when operators rotate credentials.
    """

    def __init__(
        self,
        *,
        env_var: str = "AI_TICKET_AUTH_TOKEN",
        file_env_var: str = "AI_TICKET_AUTH_TOKEN_FILE",
        reload_interval: float = 30.0,
    ) -> None:
        if reload_interval <= 0:
            raise ValueError("reload_interval must be positive")

        self._env_var = env_var
        self._file_env_var = file_env_var
        self._reload_interval = reload_interval
        self._tokens: Set[str] = set()
        self._lock = threading.RLock()
        self._last_loaded: float = 0.0
        self._file_mtime: float | None = None
        self._file_path: Path | None = None
        self.reload(force=True)

    @property
    def tokens(self) -> set[str]:
        with self._lock:
            return set(self._tokens)

    @property
    def enabled(self) -> bool:
        return self.has_tokens()

    def has_tokens(self) -> bool:
        self.reload()
        with self._lock:
            return bool(self._tokens)

    def is_valid(self, token: str | None) -> bool:
        if token is None:
            return False
        self.reload()
        with self._lock:
            return token in self._tokens

    def reload(self, *, force: bool = False) -> None:
        now = time.monotonic()
        with self._lock:
            file_path = self._resolve_file_path()
            file_mtime = self._get_file_mtime(file_path)
            should_reload = force or now - self._last_loaded >= self._reload_interval
            if file_mtime is not None and self._file_mtime is not None:
                should_reload = should_reload or file_mtime > self._file_mtime
            elif file_mtime is not None and self._file_mtime is None:
                should_reload = True

            if not should_reload:
                return

            self._tokens = self._load_tokens_from_sources(file_path=file_path)
            self._last_loaded = now
            self._file_mtime = file_mtime
            self._file_path = file_path

    def update_tokens(self, tokens: Iterable[str]) -> None:
        with self._lock:
            self._tokens = {token.strip() for token in tokens if token and token.strip()}
            self._last_loaded = time.monotonic()

    def _resolve_file_path(self) -> Path | None:
        file_value = os.environ.get(self._file_env_var)
        if not file_value:
            return None
        path = Path(file_value)
        if not path.exists():
            return None
        return path

    def _get_file_mtime(self, path: Path | None) -> float | None:
        if path is None:
            return None
        try:
            return path.stat().st_mtime
        except OSError:
            return None

    def _load_tokens_from_sources(self, *, file_path: Path | None) -> set[str]:
        tokens: set[str] = set()
        env_value = os.environ.get(self._env_var, "")
        env_tokens = {token.strip() for token in env_value.split(",") if token.strip()}
        tokens.update(env_tokens)

        if file_path is not None:
            try:
                file_tokens = {
                    line.strip()
                    for line in file_path.read_text().splitlines()
                    if line.strip()
                }
                tokens.update(file_tokens)
            except OSError:
                # Ignore file read issues; keep previously known tokens.
                pass

        return tokens


__all__ = ["TokenManager"]
