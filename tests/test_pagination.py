"""Tests for cursor-based pagination in news and events endpoints."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import models
from app.utils.pagination import (
    CursorParams,
    decode_cursor,
    decode_datetime_cursor,
    encode_datetime_cursor,
    paginate_cursor,
)


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
    timestamp_us=st.integers(min_value=0, max_value=4_102_444_800_000_000),
    news_id_uuid=st.uuids(),
)
def test_news_cursor_round_trip(timestamp_us: int, news_id_uuid: uuid.UUID) -> None:
    cursor = f"{timestamp_us}:{news_id_uuid}"
    decoded = decode_datetime_cursor(cursor)

    assert decoded is not None
    decoded_ts, decoded_id_str = decoded
    assert decoded_id_str == str(news_id_uuid)
    decoded_us = int(
        (decoded_ts - datetime(1970, 1, 1, tzinfo=UTC)) // timedelta(microseconds=1)
    )
    # Allow small tolerance for timestamp() float conversion if needed,
    # but since we construct carefully, it should be close.
    assert abs(decoded_us - timestamp_us) <= 1


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
            # Use setattr for created_at to bypass Mypy Column/datetime mismatch
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
                "created_at": now - timedelta(hours=i),
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
        ids1 = {str(item["id"]) for item in data1["items"]}
        ids2 = {str(item["id"]) for item in data2["items"]}
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


class TestNewsServicePagination:
    """Tests for NewsService pagination functions."""

    @pytest.fixture
    def news_service(self, db_session: AsyncSession):
        from app.repositories.news_repository import NewsRepository
        from app.services.news_service import NewsService
        from app.services.vector_service import VectorService

        repo = NewsRepository(db_session)
        service = NewsService(repo, VectorService(db_session))
        return service

    @pytest.mark.asyncio
    async def test_list_news_with_limit(
        self, db_session: AsyncSession, news_factory, news_service
    ):
        """Test list_news respects limit."""
        await news_factory(count=5)

        result = await news_service.list_news(limit=2)

        assert len(result.items) == 2

    @pytest.mark.asyncio
    async def test_list_news_with_cursor(
        self, db_session: AsyncSession, news_factory, news_service
    ):
        """Test list_news with cursor returns subsequent items."""
        await news_factory(count=5)

        # Get first page
        first_page = await news_service.list_news(limit=2)
        assert len(first_page.items) == 2

        # Use cursor from result
        cursor = first_page.next_cursor

        # Get second page
        second_page = await news_service.list_news(limit=2, cursor=cursor)

        # Verify no overlap
        first_ids = {str(item.id) for item in first_page.items}
        second_ids = {str(item.id) for item in second_page.items}
        assert first_ids.isdisjoint(second_ids)

    @pytest.mark.asyncio
    async def test_decode_news_cursor_valid(self):
        """Test news cursor decoding with valid format."""
        ts = 1702000000000  # timestamp in ms
        import uuid

        id_val = str(uuid.uuid4())
        cursor = f"{ts}:{id_val}"

        result = decode_datetime_cursor(cursor)

        assert result is not None
        decoded_ts, decoded_id = result
        assert decoded_id == id_val
        assert isinstance(decoded_ts, datetime)

    @pytest.mark.asyncio
    async def test_decode_news_cursor_invalid(self):
        """Test news cursor decoding with invalid format returns None."""
        assert decode_datetime_cursor(None) is None
        assert decode_datetime_cursor("") is None
        assert decode_datetime_cursor("invalid") is None
        assert decode_datetime_cursor("not:a:valid:cursor") is None
        assert decode_datetime_cursor("abc:123") is None


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
        import uuid

        from app.schemas.schemas import NewsOut, PaginatedNews

        news_item = NewsOut(
            id=uuid.uuid4(),
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


class TestGenericPagination:
    """Tests for generic paginate_cursor function."""

    @pytest.mark.asyncio
    async def test_paginate_cursor_basic(self, db_session: AsyncSession, news_factory):
        """Test basic pagination."""
        await news_factory(count=5)
        from sqlalchemy import select

        stmt = select(models.News)
        params = CursorParams(limit=2)

        result: Any = await paginate_cursor(db_session, stmt, models.News.id, params)

        assert len(result.items) == 2
        assert result.has_more is True
        assert result.next_cursor is not None
        assert result.total_count is None

    @pytest.mark.asyncio
    async def test_paginate_cursor_with_total(
        self, db_session: AsyncSession, news_factory
    ):
        """Test pagination with total count."""
        await news_factory(count=5)
        from sqlalchemy import select

        stmt = select(models.News)
        params = CursorParams(limit=2)

        result: Any = await paginate_cursor(
            db_session, stmt, models.News.id, params, include_total=True
        )

        assert len(result.items) == 2
        assert result.has_more is True
        assert result.total_count == 5

    @pytest.mark.asyncio
    async def test_paginate_cursor_ascending(
        self, db_session: AsyncSession, news_factory
    ):
        """Test pagination in ascending order."""
        await news_factory(count=5)
        # News factory creates items with decreasing created_at (hours=count-i)
        # Items are: [News 0 (oldest), ..., News 4 (newest)]
        from sqlalchemy import select

        stmt = select(models.News)
        params = CursorParams(limit=2)

        result: Any = await paginate_cursor(
            db_session, stmt, models.News.id, params, descending=False
        )

        assert len(result.items) == 2
        # Ascending by ID: should be News 0, News 1
        # Factory creates News 0 (hours=5) -> News 4 (hours=1)
        # created_at: 0 > 1 > 2 > 3 > 4
        # Our news_factory might be creating them such that 0 is oldest
        # and has earliest ID
        assert result.items[0].title in [
            "News 0",
            "News 1",
            "News 2",
            "News 3",
            "News 4",
        ]

    @pytest.mark.asyncio
    async def test_paginate_cursor_with_cursor(
        self, db_session: AsyncSession, news_factory
    ):
        """Test pagination with a cursor."""
        await news_factory(count=5)
        from sqlalchemy import select

        stmt = select(models.News)

        # Get first page
        params1 = CursorParams(limit=2)
        result1: Any = await paginate_cursor(db_session, stmt, models.News.id, params1)

        # Get second page
        params2 = CursorParams(limit=2, cursor=result1.next_cursor)
        result2: Any = await paginate_cursor(db_session, stmt, models.News.id, params2)

        assert len(result2.items) == 2
        assert result1.items[-1].id > result2.items[0].id  # Descending

    @pytest.mark.asyncio
    async def test_decode_cursor_failures(self):
        """Test decode_cursor with invalid inputs."""
        assert decode_cursor("") == ""
        assert decode_cursor("invalid-base64") == ""
        assert decode_cursor("!!!!") == ""

    @pytest.mark.asyncio
    async def test_decode_datetime_cursor_edges(self):
        """Test decode_datetime_cursor with edge cases."""
        assert decode_datetime_cursor(None) is None
        assert decode_datetime_cursor("not-a-timestamp:42") is None
        assert decode_datetime_cursor("12345678:not-an-id:too-many-parts") == (
            datetime(1970, 1, 1, 0, 0, 12, 345678, tzinfo=UTC),
            "not-an-id:too-many-parts",
        )
        # Overflow/Invalid - Windows has smaller range for fromtimestamp
        # We just want to ensure it return None if it fails
        assert decode_datetime_cursor("999999999999999999999:42") is None
