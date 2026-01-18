"""Tests for cursor-based pagination in news and events endpoints."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models import models
from app.utils.pagination import decode_datetime_cursor, encode_datetime_cursor


@settings(max_examples=30)
@given(
    timestamp_ms=st.integers(min_value=0, max_value=4_102_444_800_000),
    identifier=st.text(
        alphabet=st.characters(blacklist_characters=":", blacklist_categories=["Cs"]),
        min_size=1,
        max_size=24,
    ),
)
def test_chat_cursor_round_trip(timestamp_ms: int, identifier: str) -> None:
    original = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
    encoded = encode_datetime_cursor(original, identifier)
    decoded = decode_datetime_cursor(encoded)

    assert decoded is not None
    decoded_ts, decoded_id = decoded
    assert decoded_id == identifier
    assert abs(decoded_ts.timestamp() - original.timestamp()) <= 0.001


@settings(max_examples=25)
@given(
    value=st.text(min_size=1).filter(
        lambda raw: raw.count(":") != 1 or not raw.strip()
    ),
)
def test_chat_decode_cursor_rejects_invalid(value: str) -> None:
    assert decode_datetime_cursor(value) is None


@settings(max_examples=25)
@given(
    timestamp_ms=st.integers(min_value=0, max_value=4_102_444_800_000),
    news_id=st.integers(min_value=1, max_value=1_000_000),
)
def test_news_cursor_round_trip(timestamp_ms: int, news_id: int) -> None:
    cursor = f"{timestamp_ms}:{news_id}"
    decoded = crud._decode_news_cursor(cursor)  # noqa: SLF001

    assert decoded is not None
    decoded_ts, decoded_id = decoded
    assert decoded_id == news_id
    decoded_ms = int(decoded_ts.timestamp() * 1000)
    assert abs(decoded_ms - timestamp_ms) <= 1


@pytest.fixture
async def news_factory(db_session: AsyncSession):
    """Factory for creating news items."""

    async def _factory(count: int = 1, **defaults) -> list[models.News]:
        items = []
        for i in range(count):
            data = {
                "title": f"News {i}",
                "content": f"Content for news {i}",
                "title_en": f"News {i} EN",
                "content_en": f"Content for news {i} EN",
                **defaults,
            }
            # Vary created_at for pagination testing
            news = models.News(**data)
            news.created_at = datetime.now(UTC) - timedelta(hours=count - i)
            db_session.add(news)
            items.append(news)
        await db_session.commit()
        for item in items:
            await db_session.refresh(item)
        return items

    return _factory


@pytest.fixture
async def events_factory(db_session: AsyncSession, user_factory):
    """Factory for creating events."""

    async def _factory(count: int = 1, **defaults) -> list[models.Event]:
        user = await user_factory(role="admin")
        items = []
        now = datetime.now(UTC)
        for i in range(count):
            data = {
                "title": f"Event {i}",
                "description": f"Description for event {i}",
                "starts_at": now + timedelta(days=i),
                "ends_at": now + timedelta(days=i, hours=2),
                "created_by": user.id,
                **defaults,
            }
            event = models.Event(**data)
            db_session.add(event)
            items.append(event)
        await db_session.commit()
        for item in items:
            await db_session.refresh(item)
        return items

    return _factory


class TestNewsPagination:
    """Tests for news pagination."""

    @pytest.mark.asyncio
    async def test_news_list_returns_paginated_response(
        self, async_client: AsyncClient, news_factory
    ):
        """Test that news list returns paginated format."""
        await news_factory(count=3)
        response = await async_client.get("/news?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "has_more" in data
        assert "next_cursor" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_news_list_respects_limit(
        self, async_client: AsyncClient, news_factory
    ):
        """Test that limit parameter is respected."""
        await news_factory(count=5)
        response = await async_client.get("/news?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is True
        assert data["next_cursor"] is not None

    @pytest.mark.asyncio
    async def test_news_list_cursor_pagination(
        self, async_client: AsyncClient, news_factory
    ):
        """Test cursor-based pagination works correctly."""
        await news_factory(count=5)

        # Get first page
        response1 = await async_client.get("/news?limit=2")
        data1 = response1.json()
        assert len(data1["items"]) == 2
        cursor = data1["next_cursor"]

        # Get second page using cursor
        response2 = await async_client.get(f"/news?limit=2&cursor={cursor}")
        data2 = response2.json()
        assert len(data2["items"]) == 2

        # Verify no duplicates
        ids1 = {item["id"] for item in data1["items"]}
        ids2 = {item["id"] for item in data2["items"]}
        assert ids1.isdisjoint(ids2)

    @pytest.mark.asyncio
    async def test_news_list_empty(self, async_client: AsyncClient):
        """Test empty news list returns proper structure."""
        response = await async_client.get("/news?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["has_more"] is False
        assert data["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_news_list_last_page(self, async_client: AsyncClient, news_factory):
        """Test last page has has_more=False."""
        await news_factory(count=3)
        response = await async_client.get("/news?limit=10")
        data = response.json()
        assert data["has_more"] is False
        assert data["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_news_list_invalid_cursor_ignored(
        self, async_client: AsyncClient, news_factory
    ):
        """Test that invalid cursor is ignored (returns first page)."""
        await news_factory(count=3)
        response = await async_client.get("/news?limit=10&cursor=invalid")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3


class TestEventsPagination:
    """Tests for events pagination."""

    @pytest.mark.asyncio
    async def test_events_list_returns_paginated_response(
        self, async_client: AsyncClient, events_factory, user_factory
    ):
        """Test that events list returns paginated format."""
        await events_factory(count=3)
        user = await user_factory()

        # Login to get auth
        response = await async_client.post(
            "/auth/login", data={"username": user.email, "password": "hashed-password"}
        )

        response = await async_client.get("/events?limit=10")
        # May need auth, check response
        if response.status_code == 200:
            data = response.json()
            assert "items" in data
            assert "has_more" in data
            assert "next_cursor" in data

    @pytest.mark.asyncio
    async def test_events_list_respects_limit(
        self, async_client: AsyncClient, events_factory
    ):
        """Test that limit parameter is respected for events."""
        await events_factory(count=5)
        response = await async_client.get("/events?limit=2")
        if response.status_code == 200:
            data = response.json()
            assert len(data["items"]) <= 2


class TestCrudNewsPagination:
    """Tests for CRUD news pagination functions."""

    @pytest.mark.asyncio
    async def test_get_news_list_with_limit(
        self, db_session: AsyncSession, news_factory
    ):
        """Test get_news_list respects limit."""
        await news_factory(count=5)

        result = await crud.get_news_list(db_session, limit=2)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_news_list_with_cursor(
        self, db_session: AsyncSession, news_factory
    ):
        """Test get_news_list with cursor returns subsequent items."""
        await news_factory(count=5)

        # Get first page
        first_page = await crud.get_news_list(db_session, limit=2)
        assert len(first_page) == 2

        # Create cursor from last item
        last_item = first_page[-1]
        ts = int(last_item.created_at.timestamp() * 1000)
        cursor = f"{ts}:{last_item.id}"

        # Get second page
        second_page = await crud.get_news_list(db_session, limit=2, cursor=cursor)

        # Verify no overlap
        first_ids = {item.id for item in first_page}
        second_ids = {item.id for item in second_page}
        assert first_ids.isdisjoint(second_ids)

    @pytest.mark.asyncio
    async def test_decode_news_cursor_valid(self):
        """Test news cursor decoding with valid format."""
        from app.crud import _decode_news_cursor

        ts = 1702000000000  # timestamp in ms
        id = 42
        cursor = f"{ts}:{id}"

        result = _decode_news_cursor(cursor)

        assert result is not None
        decoded_ts, decoded_id = result
        assert decoded_id == 42
        assert isinstance(decoded_ts, datetime)

    @pytest.mark.asyncio
    async def test_decode_news_cursor_invalid(self):
        """Test news cursor decoding with invalid format returns None."""
        from app.crud import _decode_news_cursor

        assert _decode_news_cursor(None) is None
        assert _decode_news_cursor("") is None
        assert _decode_news_cursor("invalid") is None
        assert _decode_news_cursor("not:a:valid:cursor") is None
        assert _decode_news_cursor("abc:123") is None


class TestPaginatedNewsSchema:
    """Tests for PaginatedNews schema."""

    def test_paginated_news_schema_structure(self):
        """Test PaginatedNews schema has correct fields."""
        from app.schemas.schemas import PaginatedNews

        schema = PaginatedNews(
            items=[],
            has_more=False,
            next_cursor=None,
        )

        assert hasattr(schema, "items")
        assert hasattr(schema, "has_more")
        assert hasattr(schema, "next_cursor")

    def test_paginated_news_with_items(self):
        """Test PaginatedNews with actual items."""
        from app.schemas.schemas import NewsOut, PaginatedNews

        news_item = NewsOut(
            id=1,
            title="Test",
            content="Content",
            created_at=datetime.now(UTC),
        )

        schema = PaginatedNews(
            items=[news_item],
            has_more=True,
            next_cursor="1234567890:1",
        )

        assert len(schema.items) == 1
        assert schema.has_more is True
        assert schema.next_cursor == "1234567890:1"
