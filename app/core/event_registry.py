"""Type-safe event registry for the outbox worker.

RZ-010 (audit 2026-03-04): the original OutboxWorker._dispatch_event rebuilt
domain events from DB payload using ``dataclasses.make_dataclass`` + ``setattr``
in a tight loop. This is effectively an ``eval``-equivalent: any key present in
the DB payload was injected as an attribute, with no type validation whatsoever.
An attacker who could write to the outbox table (or whose data ends up stored
there) could inject arbitrary attributes into the reconstructed event objects.

This module provides a safe alternative:
- @register_event decorates concrete DomainEvent subclasses at import time.
- reconstruct_event() only instantiates registered types and only passes fields
  that the dataclass actually declares.  Unknown keys are silently dropped;
  unknown event types raise ValueError and are routed to the DLQ.
"""

from __future__ import annotations

import dataclasses
import logging

from app.core.logging import get_logger
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.events import DomainEvent

logger = get_logger(__name__)

# Registry maps event_type string (class __name__) → concrete class.
_REGISTRY: dict[str, type[DomainEvent]] = {}


def register_event(cls: type[DomainEvent]) -> type[DomainEvent]:
    """Class decorator — register a DomainEvent subclass by its class name.

    Usage::

        from app.core.event_registry import register_event
        from app.core.events import DomainEvent

        @register_event
        @dataclass
        class UserCreated(DomainEvent):
            user_id: str
            email: str
    """
    _REGISTRY[cls.__name__] = cls
    return cls


def reconstruct_event(event_type: str, payload: dict[str, Any]) -> DomainEvent:
    """Safely reconstruct a DomainEvent from an outbox payload dict.

    Parameters
    ----------
    event_type:
        String identifying the event class, stored in StoredEvent.event_type.
    payload:
        Raw JSON payload from the outbox row.

    Raises
    ------
    ValueError
        When *event_type* is not registered.  Callers should route the event
        to the dead-letter queue rather than crashing the whole worker.
    """
    cls = _REGISTRY.get(event_type)
    if cls is None:
        raise ValueError(
            f"Unknown event type {event_type!r}. "
            "Decorate the class with @register_event to enable outbox dispatch."
        )

    # Only pass keys that the dataclass actually declares — drop unknown keys
    # rather than injecting arbitrary attributes (RZ-010).
    valid_fields = {field.name for field in dataclasses.fields(cls)}
    filtered = {key: value for key, value in payload.items() if key in valid_fields}

    if unknown := set(payload) - valid_fields:
        logger.debug(
            "reconstruct_event: dropping unknown keys for %s: %s",
            event_type,
            unknown,
        )

    return cls(**filtered)
