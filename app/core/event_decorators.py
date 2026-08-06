"""
Event subscription decorators.

Provides decorator-based handler registration for cleaner code organization.
Decorated handlers are auto-registered when configure_event_handlers() is called.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, overload

if TYPE_CHECKING:
    from app.core.events import DomainEvent, EventBus
EventHandler = Callable[["DomainEvent"], Coroutine[Any, Any, None]]

# Storage for pending registrations (populated by decorators, consumed on startup)
_pending_subscriptions: list[tuple[str | type, EventHandler]] = []
_pending_all_subscriptions: list[EventHandler] = []


@overload
def subscribe(
    event_type: str,
) -> Callable[
    [EventHandler], EventHandler
]: ...  # pragma: no cover - typing-only overload


@overload
def subscribe[EventT: DomainEvent](
    event_type: type[EventT],
) -> Callable[
    [EventHandler], EventHandler
]: ...  # pragma: no cover - typing-only overload


def subscribe(
    event_type: str | type,
) -> Callable[[EventHandler], EventHandler]:
    """
    Decorator to subscribe a handler to a specific event type.

    Can be used with either an event type string or an event class:

        @subscribe("user.created")
        async def handle_user_created(event: UserCreated) -> None:
            ...

        @subscribe(UserCreated)
        async def handle_user_created(event: UserCreated) -> None:
            ...

    Args:
        event_type: Either a string event type or DomainEvent subclass.

    Returns:
        Decorator function that registers the handler.
    """

    def decorator(func: EventHandler) -> EventHandler:
        _pending_subscriptions.append((event_type, func))
        return func

    return decorator


def subscribe_all(func: EventHandler) -> EventHandler:
    """
    Decorator to subscribe a handler to all events.

    Example:
        @subscribe_all
        async def log_all_events(event: DomainEvent) -> None:
            logger.info("Event: %s", event.event_type)

    Args:
        func: The handler function to subscribe.

    Returns:
        The original function (unchanged).
    """
    _pending_all_subscriptions.append(func)
    return func


def register_decorated_handlers(bus: EventBus) -> int:
    """
    Register all decorated handlers with the given event bus.

    This should be called during application startup after all handler
    modules have been imported.

    Args:
        bus: The EventBus instance to register handlers with.

    Returns:
        Total number of handlers registered.
    """
    count = 0

    for event_type, handler in _pending_subscriptions:
        # If event_type is a class, get its event_type property
        if isinstance(event_type, type):
            # Create a temporary instance to get event_type
            # This works because event_type is a property
            # LOW-W19: Broaden the except to catch any exception that can arise
            # from constructing an event class (TypeError for missing required
            # args, ValueError/AttributeError for badly configured classes, etc.)
            # so the registration loop never aborts mid-way.
            try:
                type_str = (
                    getattr(event_type, "EVENT_TYPE", None) or event_type().event_type
                )
            except Exception:  # RZ-22-01-JUSTIFIED: handler-nak — falls back to class name for registration (reviewed TD-27-04)
                # Fall back to the fully-qualified class name so the
                # subscription is still registered under a deterministic key.
                type_str = f"{event_type.__module__}.{event_type.__name__}"
        else:
            type_str = event_type

        bus.subscribe(type_str, handler)
        count += 1

    for handler in _pending_all_subscriptions:
        bus.subscribe_all(handler)
        count += 1

    return count


def clear_pending_registrations() -> None:
    """
    Clear all pending registrations.

    Useful for testing to reset state between tests.
    """
    _pending_subscriptions.clear()
    _pending_all_subscriptions.clear()


def get_pending_count() -> int:
    """Return the number of pending registrations."""
    return len(_pending_subscriptions) + len(_pending_all_subscriptions)


__all__ = [
    "clear_pending_registrations",
    "get_pending_count",
    "register_decorated_handlers",
    "subscribe",
    "subscribe_all",
]
