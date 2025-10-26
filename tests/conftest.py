from __future__ import annotations

from collections.abc import Iterator
from unittest import mock

import pytest


class _Mocker:
    def __init__(self) -> None:
        self._patchers: list[mock._patch] = []

    def patch(self, *args, **kwargs):
        patcher = mock.patch(*args, **kwargs)
        mocked = patcher.start()
        self._patchers.append(patcher)
        return mocked

    def stop(self) -> None:
        for patcher in reversed(self._patchers):
            patcher.stop()
        self._patchers.clear()


@pytest.fixture
def mocker() -> Iterator[_Mocker]:
    helper = _Mocker()
    try:
        yield helper
    finally:
        helper.stop()
