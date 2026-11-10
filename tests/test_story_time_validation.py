"""Story writes validate effective timestamps before mutating persisted rows."""

import secrets
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.auth.security import get_password_hash
from app.core.database import async_session
from app.models import Story
from app.repositories.unit_of_work import uow_from_session
from app.schemas.stories import StoryCreate, StoryUpdate
from app.services.story_service import StoryService
from tests.test_stories_api import _login

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@pytest.mark.parametrize("schema", [StoryCreate, StoryUpdate])
@pytest.mark.parametrize(
    ("published", "expires"),
    [
        ("2026-11-10T12:00:00", "2026-11-10T16:00:00+03:00"),
        ("2026-11-10T15:00:00+03:00", "2026-11-10T13:00:00"),
        ("2026-11-10T07:00:00-05:00", "2026-11-10T16:00:00+03:00"),
    ],
)
def test_story_timestamps_normalize_before_comparison(schema, published, expires):
    data = schema(
        title="Story", short_text="Text", published_at=published, expires_at=expires
    )
    assert data.published_at == NOW
    assert data.expires_at == NOW + timedelta(hours=1)
    assert data.published_at.tzinfo is UTC
    assert data.expires_at.tzinfo is UTC


@pytest.mark.parametrize("schema", [StoryCreate, StoryUpdate])
@pytest.mark.parametrize("expires", ["2026-11-10T12:00:00Z", "2026-11-10T11:59:00Z"])
def test_story_schema_rejects_nonpositive_normalized_interval(schema, expires):
    with pytest.raises(ValidationError):
        schema(
            title="Story",
            short_text="Text",
            published_at="2026-11-10T15:00:00+03:00",
            expires_at=expires,
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"published_at": NOW + timedelta(hours=1)},
        {"published_at": NOW + timedelta(days=2)},
        {"expires_at": NOW},
        {"expires_at": NOW - timedelta(hours=1)},
        {"published_at": None},
        {"expires_at": None},
    ],
)
async def test_partial_story_interval_rejected_without_changing_row(
    db_session, story_factory, patch
):
    story = await story_factory(published_at=NOW, expires_at=NOW + timedelta(hours=1))
    story_id = story.id
    service = StoryService(uow_from_session(db_session))
    with pytest.raises(ValueError):
        await service.update_story(story_id, StoryUpdate(**patch))
    await db_session.rollback()
    async with async_session() as observer:
        persisted = await observer.get(Story, story_id)
        assert persisted is not None
        assert _utc(persisted.published_at) == NOW
        assert _utc(persisted.expires_at) == NOW + timedelta(hours=1)


@pytest.mark.parametrize(
    ("patch", "expected_publish", "expected_expiry"),
    [
        (
            {"published_at": "2026-11-10T15:30:00+03:00"},
            NOW + timedelta(minutes=30),
            NOW + timedelta(hours=1),
        ),
        ({"expires_at": "2026-11-10T14:00:00"}, NOW, NOW + timedelta(hours=2)),
        (
            {
                "published_at": NOW + timedelta(days=1),
                "expires_at": NOW + timedelta(days=2),
            },
            NOW + timedelta(days=1),
            NOW + timedelta(days=2),
        ),
        ({}, NOW, NOW + timedelta(hours=1)),
        ({"title": "Changed"}, NOW, NOW + timedelta(hours=1)),
    ],
)
async def test_valid_story_partial_and_noop_keep_omitted_times(
    db_session, story_factory, patch, expected_publish, expected_expiry
):
    story = await story_factory(published_at=NOW, expires_at=NOW + timedelta(hours=1))
    service = StoryService(uow_from_session(db_session))
    updated = await service.update_story(story.id, StoryUpdate(**patch))
    assert _utc(updated.published_at) == expected_publish
    assert _utc(updated.expires_at) == expected_expiry
    async with async_session() as observer:
        persisted = await observer.get(Story, story.id)
        assert persisted is not None
        assert _utc(persisted.published_at) == expected_publish
        assert _utc(persisted.expires_at) == expected_expiry


async def test_story_create_expiry_without_publish_is_checked_against_default(
    db_session, user_factory
):
    user = await user_factory()
    service = StoryService(uow_from_session(db_session))
    before = await db_session.scalar(select(func.count()).select_from(Story))
    with pytest.raises(ValueError):
        await service.create_story(
            StoryCreate(
                title="Story",
                short_text="Text",
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            ),
            user.id,
        )
    assert await db_session.scalar(select(func.count()).select_from(Story)) == before


@pytest.mark.parametrize(
    "times",
    [
        {},
        {"published_at": None, "expires_at": None},
        {"published_at": "2026-11-10T15:00:00+03:00"},
    ],
)
async def test_story_create_defaults_preserve_twenty_four_hour_interval(
    db_session, user_factory, times
):
    user = await user_factory()
    service = StoryService(uow_from_session(db_session))
    before = datetime.now(UTC)
    created = await service.create_story(
        StoryCreate(title="Story", short_text="Text", **times), user.id
    )
    after = datetime.now(UTC)
    assert _utc(created.expires_at) - _utc(created.published_at) == timedelta(hours=24)
    if times.get("published_at"):
        assert _utc(created.published_at) == NOW
    else:
        assert before <= _utc(created.published_at) <= after


@pytest.fixture
async def story_admin_headers(async_client, user_factory):
    password = f"{secrets.token_urlsafe(24)}aA1!"
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(password)
    )
    return await _login(async_client, admin.email, password)


@pytest.mark.parametrize("field", ["published_at", "expires_at"])
async def test_story_partial_invalid_interval_http422_not404(
    async_client, story_factory, story_admin_headers, field
):
    story = await story_factory(published_at=NOW, expires_at=NOW + timedelta(hours=1))
    value = NOW + timedelta(days=1) if field == "published_at" else NOW
    response = await async_client.patch(
        f"/stories/{story.id}",
        json={field: value.isoformat()},
        headers=story_admin_headers,
    )
    assert response.status_code == 422, response.text
    async with async_session() as observer:
        persisted = await observer.get(Story, story.id)
        assert persisted is not None
        assert _utc(persisted.published_at) == NOW
        assert _utc(persisted.expires_at) == NOW + timedelta(hours=1)


async def test_story_default_publish_invalid_expiry_http422(
    async_client, story_admin_headers
):
    response = await async_client.post(
        "/stories",
        json={
            "title": "Story",
            "short_text": "Text",
            "expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
        headers=story_admin_headers,
    )
    assert response.status_code == 422, response.text


async def test_story_no_body_patch_and_missing_story_contract(
    async_client, story_factory, story_admin_headers
):
    from uuid import uuid4

    story = await story_factory(published_at=NOW, expires_at=NOW + timedelta(hours=1))
    response = await async_client.patch(
        f"/stories/{story.id}", headers=story_admin_headers
    )
    assert response.status_code == 200, response.text
    assert _utc(datetime.fromisoformat(response.json()["published_at"])) == NOW
    missing = await async_client.patch(
        f"/stories/{uuid4()}",
        json={"published_at": NOW.isoformat()},
        headers=story_admin_headers,
    )
    assert missing.status_code == 404, missing.text


async def test_partial_story_update_refreshes_stale_persisted_counterpart(
    db_session, story_factory
):
    from sqlalchemy import update

    story = await story_factory(published_at=NOW, expires_at=NOW + timedelta(hours=4))
    story_id = story.id
    # Keep this instance loaded while another transaction changes its counterpart.
    async with async_session() as writer:
        await writer.execute(
            update(Story)
            .where(Story.id == story_id)
            .values(expires_at=NOW + timedelta(hours=1))
        )
        await writer.commit()
    assert _utc(story.expires_at) == NOW + timedelta(hours=4)
    service = StoryService(uow_from_session(db_session))
    with pytest.raises(ValueError):
        await service.update_story(
            story_id, StoryUpdate(published_at=NOW + timedelta(hours=2))
        )
    async with async_session() as observer:
        persisted = await observer.get(Story, story_id)
        assert persisted is not None
        assert _utc(persisted.published_at) == NOW
        assert _utc(persisted.expires_at) == NOW + timedelta(hours=1)


@pytest.mark.parametrize("patch", [{}, {"short_text": "Edited text"}])
async def test_story_non_time_update_preserves_legacy_interval(
    db_session, story_factory, patch
):
    story = await story_factory(published_at=NOW, expires_at=NOW - timedelta(hours=1))
    result = await StoryService(uow_from_session(db_session)).update_story(
        story.id, StoryUpdate(**patch)
    )
    assert _utc(result.published_at) == NOW
    assert _utc(result.expires_at) == NOW - timedelta(hours=1)
    if patch:
        assert result.short_text == "Edited text"


@pytest.mark.parametrize("schema", [StoryCreate, StoryUpdate])
@pytest.mark.parametrize(
    "timestamp", ["0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-12:00"]
)
def test_story_input_rejects_unrepresentable_utc_timestamps(schema, timestamp):
    with pytest.raises(ValidationError):
        schema(title="Story", short_text="Text", published_at=timestamp)


async def test_story_default_expiry_overflow_rejects_before_insert(
    db_session, user_factory
):
    user = await user_factory()
    service = StoryService(uow_from_session(db_session))
    with pytest.raises(ValueError):
        await service.create_story(
            StoryCreate(
                title="Story", short_text="Text", published_at="9999-12-31T23:59:59Z"
            ),
            user.id,
        )
    assert await db_session.scalar(select(func.count()).select_from(Story)) == 0


@pytest.mark.parametrize("field", ["published_at", "expires_at"])
async def test_story_null_time_rejects_without_other_mutations(
    async_client, story_factory, story_admin_headers, field
):
    story = await story_factory(
        title="Original", published_at=NOW, expires_at=NOW + timedelta(hours=1)
    )
    story_id = story.id
    response = await async_client.patch(
        f"/stories/{story_id}",
        json={field: None, "title": "Must not save"},
        headers=story_admin_headers,
    )
    assert response.status_code == 422, response.text
    async with async_session() as observer:
        persisted = await observer.get(Story, story_id)
        assert persisted is not None
        assert persisted.title == "Original"
        assert _utc(persisted.published_at) == NOW
        assert _utc(persisted.expires_at) == NOW + timedelta(hours=1)
