"""Quiet hours functionality.

This module handles user quiet hours (Do Not Disturb) logic for
push notification delivery.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from app.services.notifications.core import _current_local_time

if TYPE_CHECKING:
    import datetime as dt

    from app.models.models import User


def is_user_in_quiet_hours(
    user: User | None, *, now_time: dt.time | None = None
) -> bool:
    """Check if the user is currently in their quiet hours period."""
    preferences = getattr(user, "preferences", None)
    if not user or not preferences or not getattr(preferences, "dnd_enabled", False):
        return False
    start = getattr(preferences, "dnd_start", None)
    end = getattr(preferences, "dnd_end", None)
    if now_time is None:
        now_time = _current_local_time(user)
    if start is None or end is None:
        return True
    if start == end:
        return True
    if start < end:
        return bool(start <= now_time < end)
    return bool(now_time >= start or now_time < end)


def prepare_push_payload_for_user(
    payload: Mapping[str, Any],
    user: User | None,
    *,
    now_time: dt.time | None = None,
) -> dict[str, Any]:
    """Prepare a push payload for a specific user, respecting quiet hours."""
    base: dict[str, Any] = dict(payload)
    data_section = base.get("data")
    if isinstance(data_section, Mapping):
        base["data"] = dict(data_section)
    if is_user_in_quiet_hours(user, now_time=now_time):
        base["silent"] = True
        base["vibrate"] = []
        base["renotify"] = False
        base["requireInteraction"] = False
        data_payload = base.get("data")
        data_payload = dict(data_payload) if isinstance(data_payload, dict) else {}
        data_payload["dnd_suppressed"] = True
        base["data"] = data_payload
    return base
