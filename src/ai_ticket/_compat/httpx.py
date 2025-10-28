"""Compatibility importer for :mod:`httpx` with a local fallback."""

from __future__ import annotations

import importlib
import importlib.util
from types import ModuleType
from typing import Any

from . import _httpx_stub


def _load_httpx() -> ModuleType:
    spec = importlib.util.find_spec("httpx")
    if spec is not None:
        return importlib.import_module("httpx")
    return _httpx_stub


_module = _load_httpx()
__all__ = getattr(_module, "__all__", [name for name in dir(_module) if not name.startswith("_")])


def __getattr__(name: str) -> Any:
    return getattr(_module, name)


def __dir__() -> list[str]:
    return sorted(set(__all__))
