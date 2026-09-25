"""Platform release announcements (topic ``system.release``).

An administrator announces a released version once; every active user
receives one in-app notification (and Web Push where subscribed). A repeated
announcement of the same version only reaches users who have not received it,
so retries and double submissions never notify anyone twice.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.localization import DEFAULT_LOCALE, SUPPORTED_LOCALES, translate
from app.models import Notification
from app.services.notifications.core import _fetch_active_user_ids
from app.services.notifications.dedupe import lock_notification_dedupe
from app.services.notifications.delivery import create_notifications_for_users

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession

SYSTEM_RELEASE_TOPIC = "system.release"
RELEASE_VERSION_PATTERN = (
    r"^\d{1,4}\.\d{1,4}\.\d{1,6}(?:-[0-9A-Za-z][0-9A-Za-z.-]{0,31})?$"
)
_RELEASE_VERSION_RE = re.compile(RELEASE_VERSION_PATTERN)


@dataclass(frozen=True, slots=True)
class ReleaseAnnouncement:
    version: str
    created: int
    already_announced: bool


def release_dedupe_key(version: str) -> str:
    return f"system.release:{version}"


def _validated_version(version: str) -> str:
    candidate = version.strip()
    if not _RELEASE_VERSION_RE.fullmatch(candidate):
        raise ValueError("release version must be a semantic version")
    return candidate


async def _already_notified(
    db: AsyncDatabaseSession, dedupe_key: str
) -> set[uuid.UUID]:
    rows = await db.execute(
        select(Notification.user_id).where(Notification.dedupe_key == dedupe_key)
    )
    return set(rows.scalars().all())


async def announce_release(
    db: AsyncDatabaseSession,
    *,
    version: str,
    notes: Mapping[str, str | None] | None = None,
) -> ReleaseAnnouncement:
    """Notify every active user who has not yet been told about ``version``."""
    normalized = _validated_version(version)
    dedupe_key = release_dedupe_key(normalized)
    await lock_notification_dedupe(db, dedupe_key)
    notified = await _already_notified(db, dedupe_key)
    recipients = [
        user_id
        for user_id in await _fetch_active_user_ids(db)
        if user_id not in notified
    ]
    if not recipients:
        return ReleaseAnnouncement(normalized, 0, already_announced=bool(notified))

    titles: dict[str, str] = {}
    bodies: dict[str, str] = {}
    for locale in sorted(SUPPORTED_LOCALES):
        titles[locale] = translate(
            "notifications.system.release.title", locale=locale, version=normalized
        )
        custom = ((notes or {}).get(locale) or "").strip()
        bodies[locale] = custom or translate(
            "notifications.system.release.body_default", locale=locale
        )

    created = await create_notifications_for_users(
        db,
        title=titles[DEFAULT_LOCALE],
        body=bodies[DEFAULT_LOCALE],
        title_translations=titles,
        body_translations=bodies,
        type="system.message",
        url="/",
        tag=dedupe_key,
        dedupe_key=dedupe_key,
        payload_data={"category": "system", "version": normalized},
        user_ids=recipients,
        topic=SYSTEM_RELEASE_TOPIC,
        push_via_outbox_only=True,
    )
    return ReleaseAnnouncement(normalized, created, already_announced=bool(notified))


__all__ = [
    "RELEASE_VERSION_PATTERN",
    "SYSTEM_RELEASE_TOPIC",
    "ReleaseAnnouncement",
    "announce_release",
    "release_dedupe_key",
]
