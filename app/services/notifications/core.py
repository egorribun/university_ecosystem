"""Core utilities for the notifications service.

This module contains shared utilities, constants, and helper functions
used across the notifications package.
"""

from __future__ import annotations

import datetime as dt
import re
from datetime import UTC
from html import unescape
from textwrap import shorten
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app.core.database import async_session as _async_session
from app.core.localization import SUPPORTED_LOCALES, translate
from app.core.logging import get_logger
from app.models import User

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping, Sequence

    from app.core.protocols import AsyncDatabaseSession

logger = get_logger(__name__)

# Backwards compatibility for tests that patch async_session on this module.
async_session = _async_session


def _current_local_time(user: User | None = None) -> dt.time:
    """Get the current local time for a user based on their timezone."""
    tz: dt.tzinfo = UTC
    if user is not None:
        preferences = getattr(user, "preferences", None)
        raw = getattr(preferences, "timezone", None) if preferences else None
        if isinstance(raw, str):
            candidate = raw.strip()
            if candidate:
                try:
                    tz = ZoneInfo(candidate)
                except (ZoneInfoNotFoundError, ValueError):
                    tz = UTC
    now = dt.datetime.now(tz)
    current = now.timetz()
    if current.tzinfo is not None:
        current = current.replace(tzinfo=None)
    return current


def _room_label_prefixes() -> set[str]:
    """Build a set of room label prefixes for all supported locales."""
    prefixes: set[str] = set()
    for locale_code in SUPPORTED_LOCALES:
        template = translate(
            "notifications.schedule.room_label", locale=locale_code, room=""
        )
        for variant in (template, template.replace(".", "")):
            normalized = variant.strip().lower()
            if normalized:
                prefixes.add(normalized)
    prefixes.update({"room", "aud"})
    return prefixes


_ROOM_LABEL_PREFIXES = _room_label_prefixes()

_TAG_RE = re.compile(r"<[^>]+>")


def _plain_text(value: Any, *, limit: int | None = None) -> str | None:
    """Convert a value to plain text, stripping HTML and limiting length."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = unescape(_TAG_RE.sub(" ", text))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    if limit is not None and len(text) > limit:
        return shorten(text, width=limit, placeholder="…")
    return text


def _coerce_optional_text(value: Any) -> str | None:
    """Coerce a value to an optional text string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_translation_map(
    translations: Mapping[str, Any] | None,
) -> dict[str, str]:
    """Normalize a translation map to only include supported locales."""
    normalized: dict[str, str] = {}
    if not translations:
        return normalized
    for key, value in translations.items():
        if value is None:
            continue
        locale_key = str(key).strip().lower()
        if locale_key not in SUPPORTED_LOCALES:
            continue
        text = _coerce_optional_text(value)
        if text is None:
            continue
        normalized[locale_key] = text
    return normalized


def _build_delivery_row(
    notification_id: uuid.UUID,
    notification_created_at: dt.datetime,
    *,
    status: str,
    channel: str = "webpush",
    subscription_id: uuid.UUID | None = None,
    attempted_at: dt.datetime | None = None,
    delivered: bool = False,
    status_code: int | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    """Build a notification delivery row for database insertion.

    DEBT-03: ``subscription_id`` is now a first-class column rather than
    being embedded in the free-text ``detail`` field.  Callers should pass the
    ``PushSubscription.id`` for webpush rows so the deduplication index
    ``ix_notification_deliveries_dedup`` can be used for duplicate detection.
    """
    attempt_ts = attempted_at or dt.datetime.now(UTC)
    row: dict[str, Any] = {
        "notification_id": notification_id,
        "notification_created_at": notification_created_at,
        "channel": channel,
        "subscription_id": subscription_id,
        "status": status,
        "attempted_at": attempt_ts,
        "delivered_at": attempt_ts if delivered else None,
        # Keep every delivery mapping structurally identical.  PostgreSQL's
        # multi-row INSERT compiler rejects heterogeneous mappings when a
        # nullable column appears in only some rows (e.g. a successful result
        # has a status code while a failed result has a diagnostic detail).
        "status_code": int(status_code) if status_code is not None else None,
        "detail": str(detail) if detail else None,
    }
    return row


_MAX_BROADCAST_RECIPIENTS: int = 50_000


async def _fetch_active_user_ids(
    db: AsyncDatabaseSession, *, exclude: Sequence[uuid.UUID] | None = None
) -> list[uuid.UUID]:
    """Fetch IDs of all active users, optionally excluding some.

    PERF-20-01 (audit 2026-03-24): Added safety limit of 50 000 to prevent
    multi-hundred-MB result sets on large universities.  If the limit is hit,
    a warning is logged — callers should implement chunked processing.
    """
    stmt = select(User.id).where(User.is_active.is_(True))
    if exclude:
        excluded = {uid for uid in exclude if uid is not None}
        if excluded:
            stmt = stmt.where(User.id.notin_(excluded))
    stmt = stmt.limit(_MAX_BROADCAST_RECIPIENTS)
    rows = await db.execute(stmt)
    result = list(rows.scalars().all())
    if len(result) >= _MAX_BROADCAST_RECIPIENTS:
        from app.core.logging import get_logger

        get_logger(__name__).warning(
            "PERF-20-01: _fetch_active_user_ids hit safety limit of %d — "
            "implement chunked broadcast for %d+ user campuses",
            _MAX_BROADCAST_RECIPIENTS,
            _MAX_BROADCAST_RECIPIENTS,
        )
    return result


async def _fetch_admin_ids(db: AsyncDatabaseSession) -> list[uuid.UUID]:
    """Fetch IDs of all active admin users."""
    from app.models.enums import UserRole

    stmt = select(User.id).where(User.is_active.is_(True), User.role == UserRole.ADMIN)
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


def _ensure_aware(value: dt.datetime | None) -> dt.datetime:
    """Ensure a datetime value is timezone-aware (defaults to UTC)."""
    if value is None:
        return dt.datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
