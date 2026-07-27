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


def test_register_decorated_handlers_supports_strings_event_types_and_all_handlers():
    decorators.clear_pending_registrations()

    class EventWithConstant:
        EVENT_TYPE = "event.with_constant"

    async def string_handler(event):
        return None

    async def class_handler(event):
        return None

    async def all_handler(event):
        return None

    decorators.subscribe("event.by_string")(string_handler)
    decorators.subscribe(EventWithConstant)(class_handler)
    decorators.subscribe_all(all_handler)
    bus = MagicMock()

    try:
        assert decorators.get_pending_count() == 3
        assert decorators.register_decorated_handlers(bus) == 3
        bus.subscribe.assert_any_call("event.by_string", string_handler)
        bus.subscribe.assert_any_call("event.with_constant", class_handler)
        bus.subscribe_all.assert_called_once_with(all_handler)
    finally:
        decorators.clear_pending_registrations()

    assert decorators.get_pending_count() == 0
