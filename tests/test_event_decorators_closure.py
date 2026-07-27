"""Closure tests for decorator registration fallback paths."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.core import event_decorators as decorators


def test_register_decorated_handlers_falls_back_for_unconstructable_event_class():
    decorators.clear_pending_registrations()

    class BrokenEvent:
        def __init__(self):
            raise TypeError("event requires a payload")

    async def handler(event):
        return None

    decorators.subscribe(BrokenEvent)(handler)
    bus = MagicMock()

    try:
        assert decorators.register_decorated_handlers(bus) == 1
        bus.subscribe.assert_called_once_with(
            f"{BrokenEvent.__module__}.{BrokenEvent.__name__}", handler
        )
    finally:
        decorators.clear_pending_registrations()
