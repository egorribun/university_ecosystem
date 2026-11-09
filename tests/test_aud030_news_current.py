"""Live comment-page contract, including the former offset boundary."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.auth.security import get_password_hash
from app.utils.pagination import encode_datetime_cursor


def _uuid_prefix() -> int:
    # SQLite's UUID column has numeric affinity; keep a hexadecimal letter
    # in every ID so it remains text instead of becoming a number.
    return ((uuid.uuid4().int >> 64) | 0xA000000000000000) << 64


async def _news_with_author(db: AsyncSession, user_factory: Any) -> tuple[Any, Any]:
    author = await user_factory()
    news = models.News(title="Paged article", content="Article body")
    db.add(news)
    await db.flush()
    return news, author


async def _insert_comments(
    db: AsyncSession,
    news_id: uuid.UUID,
    author_id: uuid.UUID,
    rows: list[tuple[uuid.UUID, datetime]],
) -> None:
    await db.execute(
        insert(models.NewsComment),
        [
            {
                "id": comment_id,
                "news_id": news_id,
                "user_id": author_id,
                "content": f"Comment {comment_id}",
                "created_at": created_at,
            }
            for comment_id, created_at in rows
        ],
    )
    await db.commit()


@pytest.mark.asyncio
async def test_cursor_reaches_past_legacy_offset_limit_with_real_rows(
    async_client: AsyncClient, db_session: AsyncSession, user_factory: Any
) -> None:
    news, author = await _news_with_author(db_session, user_factory)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    prefix = _uuid_prefix()
    rows = [
        (uuid.UUID(int=prefix + i + 1), start + timedelta(microseconds=i))
        for i in range(10_021)
    ]
    await _insert_comments(db_session, news.id, author.id, rows)

    # Legacy clients retain the original response shape and offset limit.
    legacy = await async_client.get(
        f"/news/{news.id}/interactions", params={"limit": 20, "offset": 10_000}
    )
    assert legacy.status_code == 200
    data = legacy.json()
    assert data["comments_count"] == 10_021
    assert [item["id"] for item in data["comments"]] == [
        str(comment_id) for comment_id, _ in rows[10_000:10_020]
    ]
    assert set(data) == {"likes_count", "is_liked", "comments", "comments_count"}

    old_limit = await async_client.get(
        f"/news/{news.id}/interactions", params={"limit": 20, "offset": 10_020}
    )
    assert old_limit.status_code == 422

    # Walk the entire collection from page one without relying on offsets.
    seen: list[str] = []
    cursors: set[str] = set()
    cursor: str | None = "start"
    for _ in range(102):
        params: dict[str, str | int] = {"limit": 100}
        if cursor is not None:
            params["cursor"] = cursor
        response = await async_client.get(
            f"/news/{news.id}/interactions", params=params
        )
        assert response.status_code == 200
        page_data = response.json()
        seen.extend(item["id"] for item in page_data["comments"])
        cursor = page_data["next_cursor"]
        if cursor is None:
            break
        assert cursor not in cursors
        cursors.add(cursor)
    else:
        pytest.fail("Cursor traversal did not terminate")
    assert seen == [str(comment_id) for comment_id, _ in rows]


@pytest.mark.asyncio
async def test_cursor_survives_deleted_anchor_and_orders_timestamp_ties(
    async_client: AsyncClient, db_session: AsyncSession, user_factory: Any
) -> None:
    news, author = await _news_with_author(db_session, user_factory)
    other_news = models.News(title="Other article", content="Other body")
    db_session.add(other_news)
    await db_session.flush()
    t = datetime(2026, 2, 2, 12, 0, 0, 123456, tzinfo=UTC)
    prefix = _uuid_prefix()
    ids = [uuid.UUID(int=prefix + i) for i in (2, 4, 6, 8)]
    # Reverse insertion order makes the timestamp tie-breaker observable.
    await _insert_comments(
        db_session, news.id, author.id, [(i, t) for i in reversed(ids)]
    )
    await _insert_comments(
        db_session, other_news.id, author.id, [(uuid.UUID(int=prefix + 9), t)]
    )

    first = await async_client.get(
        f"/news/{news.id}/interactions", params={"limit": 2, "cursor": "start"}
    )
    assert first.status_code == 200
    body = first.json()
    assert [item["id"] for item in body["comments"]] == [str(ids[0]), str(ids[1])]
    cursor = body["next_cursor"]
    assert isinstance(cursor, str)

    await db_session.execute(
        delete(models.NewsComment).where(models.NewsComment.id.in_(ids[:2]))
    )
    before, after = uuid.UUID(int=prefix + 3), uuid.UUID(int=prefix + 7)
    await _insert_comments(
        db_session,
        news.id,
        author.id,
        [
            (before, t),
            (after, t),
            (uuid.UUID(int=prefix + 1), t + timedelta(microseconds=1)),
        ],
    )

    second = await async_client.get(
        f"/news/{news.id}/interactions", params={"limit": 2, "cursor": cursor}
    )
    assert second.status_code == 200
    assert [item["id"] for item in second.json()["comments"]] == [
        str(ids[2]),
        str(after),
    ]
    third = await async_client.get(
        f"/news/{news.id}/interactions",
        params={"limit": 2, "cursor": second.json()["next_cursor"]},
    )
    assert [item["id"] for item in third.json()["comments"]] == [
        str(ids[3]),
        str(uuid.UUID(int=prefix + 1)),
    ]
    fourth = await async_client.get(
        f"/news/{news.id}/interactions",
        params={"limit": 2, "cursor": third.json()["next_cursor"]},
    )
    assert fourth.status_code == 200
    assert fourth.json()["comments"] == []
    assert fourth.json()["next_cursor"] is None


@pytest.mark.parametrize(
    "cursor",
    ["", "invalid", "1:not-a-uuid", f"{10**25}:{uuid.uuid4()}", "x" * 129],
    ids=["empty", "malformed", "bad-id", "out-of-range-time", "too-long"],
)
@pytest.mark.asyncio
async def test_invalid_cursor_is_rejected(
    async_client: AsyncClient, db_session: AsyncSession, user_factory: Any, cursor: str
) -> None:
    news, _ = await _news_with_author(db_session, user_factory)
    await db_session.commit()
    response = await async_client.get(
        f"/news/{news.id}/interactions", params={"cursor": cursor}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("start_page", [False, True], ids=["continuation", "start"])
@pytest.mark.asyncio
async def test_cursor_and_nonzero_legacy_offset_are_rejected(
    async_client: AsyncClient,
    db_session: AsyncSession,
    user_factory: Any,
    start_page: bool,
) -> None:
    news, _ = await _news_with_author(db_session, user_factory)
    await db_session.commit()
    cursor = (
        "start"
        if start_page
        else encode_datetime_cursor(datetime.now(UTC), str(uuid.uuid4()))
    )
    response = await async_client.get(
        f"/news/{news.id}/interactions", params={"cursor": cursor, "offset": 1}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_legacy_and_cursor_empty_pages_have_distinct_response_shapes(
    async_client: AsyncClient, db_session: AsyncSession, user_factory: Any
) -> None:
    news, _ = await _news_with_author(db_session, user_factory)
    await db_session.commit()
    legacy = await async_client.get(f"/news/{news.id}/interactions")
    assert legacy.status_code == 200
    assert set(legacy.json()) == {
        "likes_count",
        "is_liked",
        "comments",
        "comments_count",
    }
    assert legacy.json()["comments"] == []

    opted_in = await async_client.get(
        f"/news/{news.id}/interactions", params={"cursor": "start"}
    )
    assert opted_in.status_code == 200
    assert opted_in.json()["comments"] == []
    assert "next_cursor" in opted_in.json()
    assert opted_in.json()["next_cursor"] is None


@pytest.mark.asyncio
async def test_cursor_response_preserves_anonymous_and_authenticated_like_state(
    async_client: AsyncClient, db_session: AsyncSession, user_factory: Any
) -> None:
    password = f"Aa1!{uuid.uuid4().hex}"
    author = await user_factory(hashed_password=await get_password_hash(password))
    news = models.News(title="Liked article", content="Article body")
    db_session.add(news)
    await db_session.flush()
    db_session.add(models.NewsLike(news_id=news.id, user_id=author.id))
    await _insert_comments(
        db_session, news.id, author.id, [(uuid.uuid4(), datetime.now(UTC))]
    )

    anonymous = await async_client.get(f"/news/{news.id}/interactions")
    assert anonymous.status_code == 200
    assert anonymous.json()["likes_count"] == 1
    assert anonymous.json()["is_liked"] is False
    assert "next_cursor" not in anonymous.json()
    anonymous_cursor = await async_client.get(
        f"/news/{news.id}/interactions", params={"cursor": "start"}
    )
    assert anonymous_cursor.status_code == 200
    assert anonymous_cursor.json()["is_liked"] is False
    assert anonymous_cursor.json()["next_cursor"] is None

    login = await async_client.post(
        "/auth/login", data={"username": author.email, "password": password}
    )
    assert login.status_code == 200
    token = login.cookies.get("access_token_v2")
    assert token
    authenticated = await async_client.get(
        f"/news/{news.id}/interactions",
        headers={"Authorization": f"Bearer {token}", "X-Query-Budget": "16"},
    )
    assert authenticated.status_code == 200
    assert authenticated.json()["likes_count"] == 1
    assert authenticated.json()["is_liked"] is True
    assert "next_cursor" not in authenticated.json()
    authenticated_cursor = await async_client.get(
        f"/news/{news.id}/interactions",
        params={"cursor": "start"},
        headers={"Authorization": f"Bearer {token}", "X-Query-Budget": "16"},
    )
    assert authenticated_cursor.status_code == 200
    assert authenticated_cursor.json()["is_liked"] is True
    assert authenticated_cursor.json()["next_cursor"] is None
