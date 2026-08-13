from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.core.uvloop_setup import get_loop_implementation


def test_get_loop_implementation_reports_current_policy() -> None:
    """Keep the loop-detection helper mapped in the mutmut population."""

    with patch("asyncio.get_event_loop_policy", return_value=SimpleNamespace()):
        assert get_loop_implementation() == "SimpleNamespace"
