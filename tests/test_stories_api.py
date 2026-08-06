import datetime as dt
import uuid

import pytest
from httpx import AsyncClient

import app.models as models
from app.auth.security import get_password_hash
from app.core.database import async_session
from app.services.story_cleanup import cleanup_expired_stories


async def _login(
    async_client: AsyncClient, email: str, password: str
) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.cookies.get("access_token_v2")
    return {"Authorization": f"Bearer {token}", "X-Query-Budget": "15"}


@pytest.mark.asyncio
async def test_stories_list_filters_expired(async_client: AsyncClient, story_factory):
    now = dt.datetime.now(dt.UTC)
    active = await story_factory(
        title="Active",
        published_at=now - dt.timedelta(hours=1),
        expires_at=now + dt.timedelta(hours=1),
    )
    await story_factory(
        title="Expired",
        published_at=now - dt.timedelta(hours=2),
        expires_at=now - dt.timedelta(minutes=5),
    )

    response = await async_client.get("/stories")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == str(active.id)
    assert payload[0]["title"] == active.title


@pytest.mark.asyncio
async def test_stories_list_uses_etag(
    async_client: AsyncClient, story_factory, fake_cache
):
    _ = fake_cache
    await story_factory(title="Cached story")

    headers = {"Accept-Language": "en"}

    first = await async_client.get("/stories", headers=headers)
    assert first.status_code == 200
    etag = first.headers.get("ETag")
    assert etag
    assert first.headers.get("Content-Language") == "en"

    not_modified = await async_client.get(
        "/stories", headers={**headers, "If-None-Match": etag}
    )
    assert not_modified.status_code == 304
    assert not_modified.headers.get("ETag") == etag
    assert not_modified.headers.get("Content-Language") == "en"


@pytest.mark.asyncio
async def test_story_admin_permissions(
    async_client: AsyncClient, user_factory, db_session
):
    password = "StoryAdmin123!"
    hashed = await get_password_hash(password)
    admin = await user_factory(role="admin", hashed_password=hashed)
    student = await user_factory(role="student", hashed_password=hashed)

    admin_headers = await _login(async_client, admin.email, password)
    student_headers = await _login(async_client, student.email, password)

    publish_at = dt.datetime.now(dt.UTC)
    expires_at = publish_at + dt.timedelta(hours=2)

    create_payload = {
        "title": "New story",
        "short_text": "Welcome week",
        "title_en": "New story",
        "short_text_en": "Welcome week",
        "published_at": publish_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "is_active": True,
    }

    forbidden_create = await async_client.post(
        "/stories", json=create_payload, headers=student_headers
    )
    assert forbidden_create.status_code == 403

    created = await async_client.post(
        "/stories", json=create_payload, headers=admin_headers
    )
    assert created.status_code == 200
    created_id = created.json()["id"]

    update_payload = {"short_text": "Updated copy"}

    forbidden_update = await async_client.patch(
        f"/stories/{created_id}", json=update_payload, headers=student_headers
    )
    assert forbidden_update.status_code == 403

    updated = await async_client.patch(
        f"/stories/{created_id}", json=update_payload, headers=admin_headers
    )
    assert updated.status_code == 200
    refreshed = await db_session.get(models.Story, uuid.UUID(created_id))
    assert refreshed is not None
    await db_session.refresh(refreshed)
    assert refreshed.short_text == "Updated copy"

    forbidden_delete = await async_client.delete(
        f"/stories/{created_id}", headers=student_headers
    )
    assert forbidden_delete.status_code == 403

    deleted = await async_client.delete(f"/stories/{created_id}", headers=admin_headers)
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    async with async_session() as verify_session:
        # Must cast string ID to UUID for SQLAlchemy 2.0 + SQLite
        assert await verify_session.get(models.Story, uuid.UUID(created_id)) is None


@pytest.mark.asyncio
async def test_cleanup_expired_stories_handles_naive_now(db_session, story_factory):
    past_story = await story_factory(
        title="Past",
        expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=30),
    )

    removed = await cleanup_expired_stories(db=db_session, now=dt.datetime.now(dt.UTC))
    assert removed >= 1
    async with async_session() as verify_session:
        assert await verify_session.get(models.Story, past_story.id) is None
