"""Dynamic importer that resolves to the real :mod:`anyio` when available."""

from __future__ import annotations

import importlib
import importlib.util
from types import ModuleType
from typing import Any

from . import _anyio_stub


def _load_anyio() -> ModuleType:
    spec = importlib.util.find_spec("anyio")
    if spec is not None:
        return importlib.import_module("anyio")
    return _anyio_stub


_module = _load_anyio()
__all__ = getattr(_module, "__all__", [name for name in dir(_module) if not name.startswith("_")])


def __getattr__(name: str) -> Any:
    return getattr(_module, name)


def __dir__() -> list[str]:
    return sorted(set(__all__))
