from __future__ import annotations

import pytest

from ai_ticket._compat import anyio
from ai_ticket.backends.kobold_client import aclose_all_kobold_pipelines


@pytest.fixture(autouse=True)
def _reset_kobold_pipelines() -> None:
    anyio.run(aclose_all_kobold_pipelines)
    yield
    anyio.run(aclose_all_kobold_pipelines)
