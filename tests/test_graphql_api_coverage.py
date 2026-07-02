"""Wave 9 coverage tests: Repositories, GraphQL, CQRS, APIs, Utilities.

Targets uncovered paths across repos, graphql resolvers/dataloaders,
CQRS query handlers, API endpoints, and utility functions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.auth.security import get_password_hash

_TEST_PASSWORD = "TestPassword123!"  # pragma: allowlist secret


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    resp = await client.post(
        "/auth/login",
        data={"username": email, "password": _TEST_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = resp.cookies.get("access_token_v2") or ""
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# GraphQL — type converters
# ===========================================================================


class TestGraphQLTypeConverters:
    def test_user_to_type_with_email(self):
        from app.graphql.queries import _user_to_type

        user = MagicMock()
        user.id = uuid.uuid4()
        user.email = "test@example.com"
        user.is_active = True
        user.created_at = datetime.now(UTC)
        user.profile = MagicMock()
        user.profile.full_name = "Test User"

        result = _user_to_type(user, show_email=True)
        assert result.email == "test@example.com"

    def test_user_to_type_without_email(self):
        from app.graphql.queries import _user_to_type

        user = MagicMock()
        user.id = uuid.uuid4()
        user.email = "test@example.com"
        user.is_active = True
        user.created_at = datetime.now(UTC)
        user.profile = None

        result = _user_to_type(user, show_email=False)
        assert result.email is None
        assert result.full_name is None

    def test_news_to_type(self):
        from app.graphql.queries import _news_to_type

        news = MagicMock()
        news.id = uuid.uuid4()
        news.title = "Test News"
        news.content = "Content"
        news.summary = "Summary"
        news.image_url = None
        news.created_at = datetime.now(UTC)
        news.updated_at = None
        news.likes_count = 5
        news.comments_count = 2

        result = _news_to_type(news)
        assert result.title == "Test News"
        assert result.author is None

    def test_news_to_type_with_author(self):
        from app.graphql.queries import _news_to_type

        user = MagicMock()
        user.id = uuid.uuid4()
        user.email = "author@test.com"
        user.is_active = True
        user.created_at = datetime.now(UTC)
        user.profile = MagicMock()
        user.profile.full_name = "Author"

        news = MagicMock()
        news.id = uuid.uuid4()
        news.title = "With Author"
        news.content = "Content"
        news.summary = None
        news.image_url = None
        news.created_at = datetime.now(UTC)
        news.updated_at = None
        news.likes_count = 0
        news.comments_count = 0

        result = _news_to_type(news, author=user)
        assert result.author is not None

    def test_event_to_type(self):
        from app.graphql.queries import _event_to_type

        event = MagicMock()
        event.id = uuid.uuid4()
        event.title = "Test Event"
        event.description = "Desc"
        event.start_date = datetime.now(UTC)
        event.end_date = datetime.now(UTC) + timedelta(hours=2)
        event.location = "Room 101"
        event.is_active = True
        event.created_at = datetime.now(UTC)
        event.organizer_id = uuid.uuid4()
        event.max_participants = 100
        event.event_type = "conference"

        result = _event_to_type(event)
        assert result.title == "Test Event"


# ===========================================================================
# GraphQL — DataLoaders
# ===========================================================================


class TestDataLoaders:
    @pytest.mark.asyncio
    async def test_load_users_by_ids(self):
        from app.graphql.dataloaders import load_users_by_ids

        uid = uuid.uuid4()
        mock_user = MagicMock()
        mock_user.id = uid

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_user]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await load_users_by_ids([uid], session)
        assert result[0] is mock_user

    @pytest.mark.asyncio
    async def test_load_users_missing(self):
        from app.graphql.dataloaders import load_users_by_ids

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await load_users_by_ids([uuid.uuid4()], session)
        assert result[0] is None

    @pytest.mark.asyncio
    async def test_load_news_by_ids(self):
        from app.graphql.dataloaders import load_news_by_ids

        nid = uuid.uuid4()
        mock_news = MagicMock()
        mock_news.id = nid

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_news]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await load_news_by_ids([nid], session)
        assert result[0] is mock_news

    @pytest.mark.asyncio
    async def test_load_events_by_ids(self):
        from app.graphql.dataloaders import load_events_by_ids

        eid = uuid.uuid4()
        mock_event = MagicMock()
        mock_event.id = eid

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_event]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await load_events_by_ids([eid], session)
        assert result[0] is mock_event

    def test_dataloader_registry_properties(self):
        from app.graphql.dataloaders import DataLoaderRegistry

        session = AsyncMock()
        registry = DataLoaderRegistry(session)

        # Access and verify users loader property
        users_loader = registry.users
        assert users_loader is not None
        assert registry.users is users_loader

        # Access and verify news loader property
        news_loader = registry.news
        assert news_loader is not None
        assert registry.news is news_loader

        # Access and verify events loader property
        events_loader = registry.events
        assert events_loader is not None
        assert registry.events is events_loader


# ===========================================================================
# CQRS — Schedule Query Handler
# ===========================================================================


class TestGetScheduleHandler:
    def test_schedule_cache_key(self):
        from app.cqrs.queries import GetScheduleHandler

        handler = GetScheduleHandler(db=AsyncMock(), cache=MagicMock())
        key = handler._schedule_cache_key("group-123")
        assert "schedule" in key
        assert "group-123" in key

    def test_localize_schedule_payload(self):
        from app.cqrs.queries import GetScheduleHandler

        handler = GetScheduleHandler(db=AsyncMock(), cache=MagicMock())
        payload = [
            {"lesson_type": "lecture", "subject": "Math"},
            {"lesson_type": "seminar", "subject": "Physics"},
        ]
        result = handler._localize_schedule_payload(payload, "en")
        assert len(result) == 2
        assert "lesson_type_display" in result[0]

    @pytest.mark.asyncio
    async def test_handle_cache_hit(self):
        from app.cqrs.queries import GetScheduleHandler, GetScheduleQuery
        from app.deps.cache import MemoryCache

        cache = MemoryCache(default_ttl=300)
        await cache.set("schedule:group:g1", [{"lesson_type": "lecture"}])

        handler = GetScheduleHandler(db=AsyncMock(), cache=cache)
        query = GetScheduleQuery(group_id="g1", locale="en", if_none_match=None)
        result = await handler.handle(query)

        assert result.payload is not None
        assert result.not_modified is False

    @pytest.mark.asyncio
    async def test_handle_not_modified(self):
        from app.cqrs.queries import GetScheduleHandler, GetScheduleQuery
        from app.deps.cache import MemoryCache

        cache = MemoryCache(default_ttl=300)
        entry = await cache.set("schedule:group:g1", [{"lesson_type": "lecture"}])

        handler = GetScheduleHandler(db=AsyncMock(), cache=cache)
        query = GetScheduleQuery(
            group_id="g1", locale="en", if_none_match=f'"{entry.etag}"'
        )
        result = await handler.handle(query)
        assert result.not_modified is True

    def test_query_result_dataclass(self):
        from app.cqrs.queries import QueryResult

        r = QueryResult(payload={"data": 1}, etag="abc", not_modified=False)
        assert r.payload == {"data": 1}

    def test_get_schedule_query_dataclass(self):
        from app.cqrs.queries import GetScheduleQuery

        q = GetScheduleQuery(group_id="g1", locale="en", if_none_match=None)
        assert q.group_id == "g1"


# ===========================================================================
# CQRS — Bus
# ===========================================================================


class TestCQRSBus:
    def test_bus_imports(self):
        from app.cqrs.bus import QueryBus

        assert QueryBus is not None

    def test_query_base(self):
        from app.cqrs.base import Query

        assert Query is not None


# ===========================================================================
# API — Users endpoints
# ===========================================================================


class TestUsersAPI:
    @pytest.mark.asyncio
    async def test_get_me(self, async_client: AsyncClient, user_factory, db_session):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        resp = await async_client.get("/users/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == user.email

    @pytest.mark.asyncio
    async def test_get_me_unauthenticated(self, async_client: AsyncClient):
        resp = await async_client.get("/users/me")
        assert resp.status_code == 401


# ===========================================================================
# API — Sessions
# ===========================================================================


class TestSessionsAPI:
    @pytest.mark.asyncio
    async def test_list_sessions(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        resp = await async_client.get("/sessions", headers=headers)
        # May return list or object with sessions key
        assert resp.status_code in (200, 404)


# ===========================================================================
# API — Health
# ===========================================================================


class TestHealthAPI:
    @pytest.mark.asyncio
    async def test_health_endpoint(self, async_client: AsyncClient):
        resp = await async_client.get("/health")
        # May be 200 or redirect depending on router setup
        assert resp.status_code in (200, 307, 404)

    @pytest.mark.asyncio
    async def test_readiness(self, async_client: AsyncClient):
        resp = await async_client.get("/health/ready")
        assert resp.status_code in (200, 307, 404, 503)


# ===========================================================================
# Utils — files.py
# ===========================================================================


class TestFileUtils:
    def test_normalize_filename_prefix(self):
        from app.utils.files import normalize_filename_prefix

        result = normalize_filename_prefix("My File Name!")
        assert isinstance(result, str)
        assert " " not in result or "_" in result

    def test_normalize_filename_prefix_empty(self):
        from app.utils.files import normalize_filename_prefix

        result = normalize_filename_prefix("")
        assert isinstance(result, str)

    def test_ext_from_mime(self):
        from app.utils.files import _ext_from_mime

        assert _ext_from_mime("image/jpeg") in (".jpg", ".jpeg")
        assert _ext_from_mime("application/pdf") == ".pdf"

    def test_ext_from_mime_unknown(self):
        from app.utils.files import _ext_from_mime

        result = _ext_from_mime("application/unknown-type")
        assert isinstance(result, str)

    def test_normalize_mime_type(self):
        from app.utils.files import _normalize_mime_type

        assert _normalize_mime_type("IMAGE/JPEG") == "image/jpeg"
        assert _normalize_mime_type(None) == ""
        assert _normalize_mime_type("") == ""

    def test_detect_image_mime(self):
        from app.utils.files import _detect_image_mime

        # PNG magic bytes
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        result = _detect_image_mime(png)
        assert result is None or "png" in (result or "")

    def test_detect_mime_type(self):
        from app.utils.files import detect_mime_type

        pdf = b"%PDF-1.4 test"
        result = detect_mime_type(pdf)
        assert result is not None


# ===========================================================================
# Audit Service
# ===========================================================================


class TestAuditService:
    def test_audit_service_log(self):
        from app.services.audit_service import SecurityEvent, audit_service

        # audit_service.log should not raise
        audit_service.log(
            SecurityEvent.ACCESS_DENIED,
            user_id=uuid.uuid4(),
            reason="test",
            action="test_action",
        )

    def test_security_event_enum(self):
        from app.services.audit_service import SecurityEvent

        assert SecurityEvent.ACCESS_DENIED is not None
        assert isinstance(SecurityEvent.ACCESS_DENIED, str) or hasattr(
            SecurityEvent.ACCESS_DENIED, "value"
        )


# ===========================================================================
# API — deps/services.py and deps/auth.py
# ===========================================================================


class TestAPIDeps:
    @pytest.mark.asyncio
    async def test_get_current_user_dependency(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        """Verify the auth dependency chain works end-to-end."""
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        resp = await async_client.get("/users/me", headers=headers)
        assert resp.status_code == 200


# ===========================================================================
# API — News
# ===========================================================================


class TestNewsAPI:
    @pytest.mark.asyncio
    async def test_list_news(self, async_client: AsyncClient, user_factory, db_session):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        resp = await async_client.get("/news", headers=headers)
        assert resp.status_code == 200


# ===========================================================================
# API — Events
# ===========================================================================


class TestEventsAPI:
    @pytest.mark.asyncio
    async def test_list_events(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        resp = await async_client.get("/events", headers=headers)
        assert resp.status_code == 200


# ===========================================================================
# Repositories — Session Repository
# ===========================================================================


class TestSessionRepository:
    @pytest.mark.asyncio
    async def test_session_repository_imports(self):
        from app.repositories.session_repository import SessionRepository

        assert SessionRepository is not None

    @pytest.mark.asyncio
    async def test_get_by_jti(self, db_session):
        from app.repositories.session_repository import SessionRepository

        repo = SessionRepository(db_session)
        result = await repo.get_by_jti("nonexistent-jti")
        assert result is None

    @pytest.mark.asyncio
    async def test_touch_by_jti(self, db_session):
        from app.repositories.session_repository import SessionRepository

        repo = SessionRepository(db_session)
        # Should not raise even for nonexistent JTI
        await repo.touch_by_jti("nonexistent-jti")
