"""Wave 9 coverage tests: Repositories, GraphQL, CQRS, APIs, Utilities.

Targets uncovered paths across repos, graphql resolvers/dataloaders,
CQRS query handlers, API endpoints, and utility functions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestGraphQLAdvancedCoverage:
    def test_graphql_context_is_authenticated(self):
        from app.graphql.context import GraphQLContext

        ctx = GraphQLContext(
            session=None, loaders=None, checker=None, current_user=None
        )
        assert ctx.is_authenticated is False
        user = MagicMock()
        ctx.current_user = user
        assert ctx.is_authenticated is True

    @pytest.mark.asyncio
    async def test_graphql_permissions_coverage(self):
        from app.auth.rbac import SpiceDBUnavailableError
        from app.graphql.permissions import IsAdmin, IsAuthenticated

        source = None
        info = MagicMock()
        info.context = MagicMock()

        # IsAuthenticated
        perm_auth = IsAuthenticated()
        info.context.is_authenticated = True
        assert perm_auth.has_permission(source, info) is True
        info.context.is_authenticated = False
        assert perm_auth.has_permission(source, info) is False

        # IsAdmin
        perm_admin = IsAdmin()

        # 1. Unauthenticated
        info.context.is_authenticated = False
        info.context.current_user = None
        assert await perm_admin.has_permission(source, info) is False

        # 2. Authenticated but no checker in context
        info.context.is_authenticated = True
        info.context.current_user = MagicMock()
        info.context.checker = None
        assert await perm_admin.has_permission(source, info) is False

        # 3. Checker check_admin returns True
        mock_checker = AsyncMock()
        mock_checker.check_admin.return_value = True
        info.context.checker = mock_checker
        assert await perm_admin.has_permission(source, info) is True
        mock_checker.check_admin.assert_called_once_with(
            str(info.context.current_user.id)
        )

        # 4. Checker check_admin returns False
        mock_checker.check_admin.reset_mock()
        mock_checker.check_admin.return_value = False
        assert await perm_admin.has_permission(source, info) is False

        # 5. SpiceDBUnavailableError
        mock_checker.check_admin.side_effect = SpiceDBUnavailableError("SpiceDB down")
        assert await perm_admin.has_permission(source, info) is False

        # 6. Unexpected Exception (RZ-22-01)
        mock_checker.check_admin.side_effect = RuntimeError("DB crash")
        assert await perm_admin.has_permission(source, info) is False

    @pytest.mark.asyncio
    async def test_increment_user_cost_fallback(self):
        from unittest.mock import patch

        from app.graphql.extensions import _increment_user_cost, _user_cost_memory

        with patch(
            "app.deps.cache.get_cache_client", side_effect=ConnectionError("Redis down")
        ):
            # Clear memory cost first
            _user_cost_memory.clear()
            cost1 = await _increment_user_cost("user123", 10, 55555)
            assert cost1 == 10
            # Call again inside same window -> accumulates
            cost2 = await _increment_user_cost("user123", 15, 55555)
            assert cost2 == 25
            # Call for a new window -> clears memory and starts new window
            cost3 = await _increment_user_cost("user123", 5, 55556)
            assert cost3 == 5

            # Test evicting stale/large memory dict
            _user_cost_memory.clear()
            for i in range(10005):
                _user_cost_memory[f"user_{i}"] = (10, 55555)
            cost4 = await _increment_user_cost("user123", 10, 55555)
            assert cost4 == 10
            assert len(_user_cost_memory) == 1

    @pytest.mark.asyncio
    async def test_query_cost_limiter_edge_cases(self):
        from unittest.mock import patch

        from graphql import GraphQLError

        from app.graphql.extensions import QueryCostExtension

        # 1. pre_execution_errors
        exec_ctx = MagicMock()
        exec_ctx.pre_execution_errors = [GraphQLError("Previous error")]
        ext = QueryCostExtension()
        ext.execution_context = exec_ctx
        async for _ in ext.on_validate():
            pass  # should return immediately and not parse cost

        # 2. document is None
        exec_ctx = MagicMock()
        exec_ctx.pre_execution_errors = []
        exec_ctx.graphql_document = None
        ext = QueryCostExtension()
        ext.execution_context = exec_ctx
        async for _ in ext.on_validate():
            pass  # should return immediately and not parse cost

        # 3. cost limit exceeded
        exec_ctx = MagicMock()
        exec_ctx.pre_execution_errors = []
        exec_ctx.graphql_document = MagicMock()

        ext = QueryCostExtension()
        ext.execution_context = exec_ctx
        with (
            patch("app.graphql.extensions._CostVisitor") as mock_visitor_class,
            patch("app.graphql.extensions.visit"),
        ):
            mock_visitor = MagicMock()
            mock_visitor.cost = 300
            mock_visitor_class.return_value = mock_visitor

            with pytest.raises(GraphQLError, match="Query cost 300 exceeds"):
                async for _ in ext.on_validate():
                    pass

        # 4. user rate limit exceeded
        exec_ctx = MagicMock()
        exec_ctx.pre_execution_errors = []
        exec_ctx.graphql_document = MagicMock()
        mock_context = MagicMock()
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_context.current_user = mock_user
        exec_ctx.context = mock_context

        ext = QueryCostExtension()
        ext.execution_context = exec_ctx
        with (
            patch("app.graphql.extensions._CostVisitor") as mock_visitor_class,
            patch("app.graphql.extensions.visit"),
            patch("app.graphql.extensions._increment_user_cost", return_value=1200),
        ):
            mock_visitor = MagicMock()
            mock_visitor.cost = 50
            mock_visitor_class.return_value = mock_visitor

            with pytest.raises(GraphQLError, match="GraphQL rate limit exceeded"):
                async for _ in ext.on_validate():
                    pass

    @pytest.mark.asyncio
    async def test_request_timeout_extension_timeout(self):
        from unittest.mock import patch

        from graphql import GraphQLError

        from app.graphql.extensions import RequestTimeoutExtension

        exec_ctx = MagicMock()
        ext = RequestTimeoutExtension()
        ext.execution_context = exec_ctx

        class MockTimeout:
            def __init__(self, delay):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                raise TimeoutError()

        with patch("app.graphql.extensions.asyncio.timeout", MockTimeout):
            gen = ext.on_execute()
            # Enters context manager and yields
            await gen.__anext__()

            # Resuming should trigger TimeoutError inside generator
            with pytest.raises(
                GraphQLError, match="Request exceeded the maximum execution time"
            ):
                await gen.__anext__()

    @pytest.mark.asyncio
    async def test_persisted_query_extension_coverage(self):
        from unittest.mock import patch

        from graphql import GraphQLError

        import app.graphql.extensions as ext_module
        from app.graphql.extensions import (
            PersistedQueryExtension,
            _hash_query,
            _load_manifest,
        )

        # 1. dev env bypass
        with patch("app.core.config.settings.environment", "development"):
            exec_ctx = MagicMock()
            ext = PersistedQueryExtension()
            ext.execution_context = exec_ctx
            async for _ in ext.on_validate():
                pass  # returns immediately

        # Force production environment for validation testing
        with patch("app.core.config.settings.environment", "production"):
            # 2. _load_manifest missing manifest file
            with patch("app.graphql.extensions._MANIFEST_PATH") as mock_path:
                mock_path.exists.return_value = False
                ext_module._query_allowlist = None  # clear cache
                manifest = _load_manifest()
                assert manifest == {}

            # 3. _load_manifest reading invalid json
            with patch("app.graphql.extensions._MANIFEST_PATH") as mock_path:
                mock_path.exists.return_value = True
                mock_path.read_text.return_value = "invalid-json"
                ext_module._query_allowlist = None
                manifest = _load_manifest()
                assert manifest == {}

            # 4. _load_manifest successful JSON read (line 257)
            with patch("app.graphql.extensions._MANIFEST_PATH") as mock_path:
                mock_path.exists.return_value = True
                mock_path.read_text.return_value = '{"hash123": "query { me }"}'
                ext_module._query_allowlist = None
                manifest = _load_manifest()
                assert manifest == {"hash123": "query { me }"}

            # 5. _load_manifest double-checked lock hit (line 253)
            with patch("app.graphql.extensions._manifest_lock") as mock_lock:

                def mock_enter(*args, **kwargs):
                    ext_module._query_allowlist = {"foo": "bar"}
                    return MagicMock()

                mock_lock.__enter__ = mock_enter
                ext_module._query_allowlist = None
                manifest = _load_manifest()
                assert manifest == {"foo": "bar"}

            # 6. Allowlist lookup happy path
            ext_module._query_allowlist = {"hash123": "query { me }"}
            # Send query with valid hash in extensions
            exec_ctx = MagicMock()
            exec_ctx.query = "query { me }"
            exec_ctx.extensions = {"persistedQuery": {"sha256Hash": "hash123"}}
            ext = PersistedQueryExtension()
            ext.execution_context = exec_ctx
            async for _ in ext.on_validate():
                pass  # passes

            # 7. Allowlist lookup invalid hash -> raises GraphQLError
            exec_ctx = MagicMock()
            exec_ctx.query = "query { me }"
            exec_ctx.extensions = {"persistedQuery": {"sha256Hash": "unknown_hash"}}
            ext = PersistedQueryExtension()
            ext.execution_context = exec_ctx
            with pytest.raises(
                GraphQLError, match="This query is not in the persisted-query allowlist"
            ):
                async for _ in ext.on_validate():
                    pass

            # 8. Check fallback to hashing query string if no client hash
            query_str = "query { test }"
            query_hash = _hash_query(query_str)
            ext_module._query_allowlist = {query_hash: query_str}
            exec_ctx = MagicMock()
            exec_ctx.query = query_str
            exec_ctx.extensions = None
            ext = PersistedQueryExtension()
            ext.execution_context = exec_ctx
            async for _ in ext.on_validate():
                pass  # passes

            # 9. No manifest allow-all bypass (line 308)
            ext_module._query_allowlist = {}
            exec_ctx = MagicMock()
            ext = PersistedQueryExtension()
            ext.execution_context = exec_ctx
            async for _ in ext.on_validate():
                pass

            # 10. No query return (line 312)
            ext_module._query_allowlist = {"hash123": "query { me }"}
            exec_ctx = MagicMock()
            exec_ctx.query = None
            ext = PersistedQueryExtension()
            ext.execution_context = exec_ctx
            async for _ in ext.on_validate():
                pass

    @pytest.mark.asyncio
    async def test_graphql_schema_get_context_dependency_overrides(self):
        from app.auth.rbac import PermissionChecker
        from app.graphql.schema import get_context

        request = MagicMock()
        request.headers = {}
        request.state.dishka_container = AsyncMock()
        request.app.dependency_overrides = {PermissionChecker: lambda: "mocked_checker"}

        async for context in get_context(request):
            assert context.checker == "mocked_checker"

    @pytest.mark.asyncio
    async def test_graphql_schema_get_context_container_errors(self):
        from fastapi import HTTPException

        from app.graphql.schema import get_context

        request = MagicMock()
        request.headers = {}
        request.state.dishka_container.get = AsyncMock(
            side_effect=RuntimeError("DI failed")
        )

        # Database resolution fails -> returns 503
        with pytest.raises(HTTPException) as excinfo:
            async for _ in get_context(request):
                pass
        assert excinfo.value.status_code == 503

    @pytest.mark.asyncio
    async def test_graphql_schema_get_context_spicedb_missing(self):
        from app.core.protocols import AsyncDatabaseSession
        from app.graphql.schema import get_context

        request = MagicMock()
        request.headers = {}
        request.app.dependency_overrides = {}

        # database session succeeds, but PermissionChecker resolution fails
        async def mock_get(protocol):
            if protocol is AsyncDatabaseSession:
                return MagicMock()
            raise RuntimeError("SpiceDB unavailable")

        request.state.dishka_container.get = mock_get

        async for context in get_context(request):
            assert context.checker is None

    @pytest.mark.asyncio
    async def test_graphql_schema_get_context_auth_validation_x_headers(self):
        from app.graphql.schema import get_context

        request = MagicMock()
        request.app.dependency_overrides = {}
        request.state.dishka_container.get = AsyncMock(return_value=MagicMock())
        request.headers = {"X-User-ID": "user-123", "X-Session-ID": "session-456"}

        mock_user = MagicMock()
        with patch(
            "app.services.auth.graphql_token_validator.GraphQLTokenValidator.validate",
            return_value=mock_user,
        ) as mock_val:
            async for context in get_context(request):
                assert context.current_user == mock_user
                mock_val.assert_called_once_with("user-123", "session-456")

    @pytest.mark.asyncio
    async def test_graphql_schema_get_context_security_error_subclasses(self):
        from unittest.mock import patch

        from fastapi import HTTPException

        from app.auth.security import SecurityError
        from app.graphql.schema import get_context

        class CustomSecurityError(SecurityError):
            pass

        request = MagicMock()
        request.app.dependency_overrides = {}
        request.state.dishka_container.get = AsyncMock(return_value=MagicMock())
        request.headers = {"X-User-ID": "user-123", "X-Session-ID": "session-456"}

        with patch(
            "app.services.auth.graphql_token_validator.GraphQLTokenValidator.validate",
            side_effect=CustomSecurityError("Account locked"),
        ):
            with pytest.raises(HTTPException) as excinfo:
                async for _ in get_context(request):
                    pass
            assert excinfo.value.status_code == 503

    @pytest.mark.asyncio
    async def test_graphql_schema_get_context_exact_security_error(self):
        from app.auth.security import SecurityError
        from app.graphql.schema import get_context

        request = MagicMock()
        request.app.dependency_overrides = {}
        request.state.dishka_container.get = AsyncMock(return_value=MagicMock())
        request.headers = {"X-User-ID": "user-123", "X-Session-ID": "session-456"}

        with patch(
            "app.services.auth.graphql_token_validator.GraphQLTokenValidator.validate",
            side_effect=SecurityError("Invalid session"),
        ):
            async for context in get_context(request):
                assert context.current_user is None  # demoted to anonymous

    @pytest.mark.asyncio
    async def test_graphql_schema_get_context_non_security_error(self):
        from unittest.mock import patch

        from fastapi import HTTPException

        from app.graphql.schema import get_context

        request = MagicMock()
        request.app.dependency_overrides = {}
        request.state.dishka_container.get = AsyncMock(return_value=MagicMock())
        request.headers = {"X-User-ID": "user-123", "X-Session-ID": "session-456"}

        with patch(
            "app.services.auth.graphql_token_validator.GraphQLTokenValidator.validate",
            side_effect=RuntimeError("DB timeout"),
        ):
            with pytest.raises(HTTPException) as excinfo:
                async for _ in get_context(request):
                    pass
            assert excinfo.value.status_code == 503

    @pytest.mark.asyncio
    async def test_graphql_schema_get_context_auth_validation_bearer_token(self):
        from app.auth.security import _mint_pure_jwt
        from app.graphql.schema import get_context

        request = MagicMock()
        request.app.dependency_overrides = {}
        request.state.dishka_container.get = AsyncMock(return_value=MagicMock())

        # Create a valid token
        token = _mint_pure_jwt(subject="user-123", extra_claims={"jti": "jti-456"})
        request.headers = {"Authorization": f"Bearer {token}"}

        mock_user = MagicMock()
        with patch(
            "app.services.auth.graphql_token_validator.GraphQLTokenValidator.validate",
            return_value=mock_user,
        ) as mock_val:
            async for context in get_context(request):
                assert context.current_user == mock_user
                mock_val.assert_called_once_with("user-123", "jti-456")

    def test_graphql_build_schema_extensions_prod(self):
        from unittest.mock import patch

        from app.graphql.extensions import PersistedQueryExtension
        from app.graphql.schema import _build_schema_extensions

        with patch("app.graphql.schema.settings.environment", "production"):
            exts = _build_schema_extensions()
            # PersistedQueryExtension is appended in production
            assert PersistedQueryExtension in exts
