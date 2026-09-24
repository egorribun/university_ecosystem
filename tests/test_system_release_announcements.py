"""Platform release announcements reach every active user exactly once."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

import app.routers.notifications as push_router
from app import models
from app.core.notification_contract import CANONICAL_NOTIFICATION_TOPICS
from app.models.enums import UserRole
from app.schemas.notifications import ReleaseAnnouncementRequest
from app.services.notifications.system_release import (
    SYSTEM_RELEASE_TOPIC,
    ReleaseAnnouncement,
    announce_release,
    release_dedupe_key,
)
from tests.conftest import call_injected

NO_PUSH = patch(
    "app.services.notifications.delivery._is_push_configured", return_value=False
)


async def _rows(db_session) -> list[models.Notification]:
    result = await db_session.execute(select(models.Notification))
    return list(result.scalars())


def test_release_topic_is_canonical() -> None:
    assert SYSTEM_RELEASE_TOPIC == "system.release"
    assert SYSTEM_RELEASE_TOPIC in CANONICAL_NOTIFICATION_TOPICS
    assert release_dedupe_key("1.4.0") == "system.release:1.4.0"


@pytest.mark.asyncio
async def test_announcement_notifies_active_users_once(
    db_session, user_factory
) -> None:
    first = await user_factory()
    second = await user_factory()
    await user_factory(is_active=False)

    with NO_PUSH:
        announced = await announce_release(db_session, version=" 1.4.0 ")
        repeated = await announce_release(db_session, version="1.4.0")

    assert announced == ReleaseAnnouncement("1.4.0", 2, already_announced=False)
    assert repeated == ReleaseAnnouncement("1.4.0", 0, already_announced=True)
    rows = await _rows(db_session)
    assert {row.user_id for row in rows} == {first.id, second.id}
    row = rows[0]
    assert row.type == "system.message"
    assert row.url == "/"
    assert row.dedupe_key == "system.release:1.4.0"
    assert row.title == "Вышла новая версия платформы 1.4.0"
    assert row.title_en == "Platform version 1.4.0 is available"
    assert row.body == "Обновите страницу, чтобы получить последние улучшения."
    assert row.body_en == "Reload the page to get the latest improvements."


@pytest.mark.asyncio
async def test_repeat_reaches_only_users_who_missed_it(
    db_session, user_factory
) -> None:
    await user_factory()
    with NO_PUSH:
        await announce_release(db_session, version="2.0.0-rc.1")
    newcomer = await user_factory()
    with NO_PUSH:
        catch_up = await announce_release(
            db_session,
            version="2.0.0-rc.1",
            notes={"ru": "  Новый мессенджер  ", "en": "New messenger", "de": "x"},
        )

    assert catch_up == ReleaseAnnouncement("2.0.0-rc.1", 1, already_announced=True)
    latest = [row for row in await _rows(db_session) if row.user_id == newcomer.id]
    assert [row.body for row in latest] == ["Новый мессенджер"]
    assert [row.body_en for row in latest] == ["New messenger"]


@pytest.mark.asyncio
async def test_announcement_without_recipients_creates_nothing(db_session) -> None:
    with NO_PUSH:
        result = await announce_release(db_session, version="1.0.0")
    assert result == ReleaseAnnouncement("1.0.0", 0, already_announced=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["", "1.4", "v1.4.0", "1.4.0-", "1.4.0 beta"])
async def test_service_rejects_non_semantic_versions(version: str) -> None:
    with pytest.raises(
        ValueError, match=r"^release version must be a semantic version$"
    ):
        await announce_release(AsyncMock(), version=version)


@pytest.mark.parametrize("version", ["1.4", "v1.4.0", "1.4.0+build", "1" * 49])
def test_request_schema_rejects_non_semantic_versions(version: str) -> None:
    with pytest.raises(ValidationError):
        ReleaseAnnouncementRequest(version=version)


def _admin() -> MagicMock:
    user = MagicMock()
    user.role = UserRole.ADMIN
    user.id = uuid.uuid4()
    return user


@pytest.mark.asyncio
async def test_route_requires_an_admin() -> None:
    user = _admin()
    user.role = UserRole.TEACHER
    with (
        patch("app.routers.notifications.resolve_locale", return_value="en"),
        patch(
            "app.routers.notifications.announce_release", new=AsyncMock()
        ) as announce,
        pytest.raises(HTTPException) as exc,
    ):
        await call_injected(
            push_router.announce_platform_release,
            data=ReleaseAnnouncementRequest(version="1.4.0"),
            request=MagicMock(),
            user=user,
            provides={"AsyncDatabaseSession": AsyncMock()},
        )
    assert exc.value.status_code == 403
    announce.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_is_rate_limited() -> None:
    from app.core.ratelimit import RateLimitExceeded, RateLimitInfo

    info = RateLimitInfo(allowed=False, remaining=0, retry_after=7)
    with (
        patch("app.routers.notifications.resolve_locale", return_value="en"),
        patch(
            "app.routers.notifications.enforce_rate_limit",
            side_effect=RateLimitExceeded(info),
        ),
        patch(
            "app.routers.notifications.announce_release", new=AsyncMock()
        ) as announce,
        pytest.raises(HTTPException) as exc,
    ):
        await call_injected(
            push_router.announce_platform_release,
            data=ReleaseAnnouncementRequest(version="1.4.0"),
            request=MagicMock(),
            user=_admin(),
            provides={"AsyncDatabaseSession": AsyncMock()},
        )
    assert exc.value.status_code == 429
    assert exc.value.detail["retry_after"] == 7
    announce.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_announces_and_commits() -> None:
    db = AsyncMock()
    user = _admin()
    with (
        patch("app.routers.notifications.resolve_locale", return_value="en"),
        patch("app.routers.notifications.enforce_rate_limit", new=AsyncMock()) as limit,
        patch(
            "app.routers.notifications.announce_release",
            new=AsyncMock(return_value=ReleaseAnnouncement("1.4.0", 3, False)),
        ) as announce,
    ):
        response = await call_injected(
            push_router.announce_platform_release,
            data=ReleaseAnnouncementRequest(
                version="1.4.0", notes_ru="Заметки", notes_en="Notes"
            ),
            request=MagicMock(),
            user=user,
            provides={"AsyncDatabaseSession": db},
        )

    assert response.model_dump() == {
        "version": "1.4.0",
        "created": 3,
        "already_announced": False,
    }
    announce.assert_awaited_once_with(
        db, version="1.4.0", notes={"ru": "Заметки", "en": "Notes"}
    )
    db.commit.assert_awaited_once()
    assert limit.await_args.kwargs["identifier"] == f"notifications:release:{user.id}"
    assert limit.await_args.kwargs["limit"] == 5
    assert limit.await_args.kwargs["window_seconds"] == 3600


@pytest.mark.asyncio
async def test_announcement_delivery_call_is_exact(db_session, user_factory) -> None:
    member = await user_factory()
    deliver = AsyncMock(return_value=1)
    with patch(
        "app.services.notifications.system_release.create_notifications_for_users",
        deliver,
    ):
        result = await announce_release(
            db_session, version="1.4.0", notes={"en": "  New messenger  "}
        )

    assert result == ReleaseAnnouncement("1.4.0", 1, already_announced=False)
    deliver.assert_awaited_once()
    assert deliver.await_args.kwargs == {
        "title": "Platform version 1.4.0 is available",
        "body": "New messenger",
        "title_translations": {
            "en": "Platform version 1.4.0 is available",
            "ru": "Вышла новая версия платформы 1.4.0",
        },
        "body_translations": {
            "en": "New messenger",
            "ru": "Обновите страницу, чтобы получить последние улучшения.",
        },
        "type": "system.message",
        "url": "/",
        "tag": "system.release:1.4.0",
        "dedupe_key": "system.release:1.4.0",
        "payload_data": {"category": "system", "version": "1.4.0"},
        "user_ids": [member.id],
        "topic": "system.release",
    }
