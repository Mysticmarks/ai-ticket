"""Minimal anyio-compatible helpers built on top of asyncio."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

sleep = asyncio.sleep


class Semaphore(AbstractAsyncContextManager):
    def __init__(self, value: int) -> None:
        self._sem = asyncio.Semaphore(value)

    async def __aenter__(self) -> "Semaphore":
        await self._sem.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._sem.release()


class CancelScope:
    def __init__(self, tasks: list[asyncio.Task[Any]]) -> None:
        self._tasks = tasks

    def cancel(self) -> None:
        for task in list(self._tasks):
            task.cancel()


class TaskGroup(AbstractAsyncContextManager):
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[Any]] = []
        self.cancel_scope = CancelScope(self._tasks)

    async def __aenter__(self) -> "TaskGroup":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        errors: list[BaseException] = []
        while self._tasks:
            task = self._tasks.pop(0)
            try:
                await task
            except asyncio.CancelledError:
                continue
            except Exception as error:  # pragma: no cover - defensive
                errors.append(error)
        if errors and exc is None:
            raise errors[0]

    def start_soon(self, func: Callable[..., Awaitable[Any]], /, *args: Any) -> None:
        self._tasks.append(asyncio.create_task(func(*args)))


class Event:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def set(self) -> None:
        self._event.set()

    async def wait(self) -> None:
        await self._event.wait()


class _LowLevelModule:
    @staticmethod
    async def checkpoint() -> None:
        await asyncio.sleep(0)


lowlevel = _LowLevelModule()


def create_task_group() -> TaskGroup:
    return TaskGroup()


def run(func: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
    return asyncio.run(func(*args, **kwargs))


__all__ = [
    "Semaphore",
    "TaskGroup",
    "Event",
    "CancelScope",
    "create_task_group",
    "sleep",
    "run",
    "lowlevel",
]

