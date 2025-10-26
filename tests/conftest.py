import pathlib
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


@pytest.fixture
def mocker():
    patches: list[mock._patch] = []

    def _patch(target: str, *args, **kwargs):
        patcher = mock.patch(target, *args, **kwargs)
        patched = patcher.start()
        patches.append(patcher)
        return patched

    yield SimpleNamespace(patch=_patch)

    while patches:
        patches.pop().stop()
