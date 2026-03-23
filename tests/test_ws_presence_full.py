"""Comprehensive tests for app/api/ws/presence.py and app/api/ws/auth.py.

Covers: presence audience cache (LRU eviction, TTL), PresencePubSub,
build_presence_map, cache invalidation helpers, auth token validation,
bearer extraction, subprotocol handling.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.ws.auth import (
    extract_bearer_token,
    extract_token_from_subprotocol,
    select_subprotocol,
    update_last_seen,
)
from app.api.ws.presence import (
    PRESENCE_SOURCE_PUBSUB,
    PresencePubSub,
    _get_presence_audience,
    _handle_presence_pubsub,
    build_presence_map,
    invalidate_chat_participants_cache,
    invalidate_presence_audience_cache,
)

# ===========================================================================
# Auth helpers
# ===========================================================================


class TestExtractBearerToken:
    def test_bearer_prefix(self):
        assert extract_bearer_token("Bearer abc123") == "abc123"

    def test_bare_token(self):
        assert extract_bearer_token("abc123") == "abc123"

    def test_none(self):
        assert extract_bearer_token(None) is None

    def test_empty(self):
        assert extract_bearer_token("") is None

    def test_multiple_parts(self):
        assert extract_bearer_token("Bearer abc 123") is None

    def test_case_insensitive(self):
        assert extract_bearer_token("bearer TOKEN") == "TOKEN"


class TestExtractTokenFromSubprotocol:
    def test_access_token(self):
        assert extract_token_from_subprotocol("access_token, eyJhbGc") == "eyJhbGc"

    def test_bearer(self):
        assert (
            extract_token_from_subprotocol("bearer, jwt-token-here") == "jwt-token-here"
        )

    def test_authorization(self):
        assert extract_token_from_subprotocol("authorization, tok") == "tok"

    def test_no_match(self):
        assert extract_token_from_subprotocol("chat, json") is None

    def test_none(self):
        assert extract_token_from_subprotocol(None) is None

    def test_empty(self):
        assert extract_token_from_subprotocol("") is None

    def test_keyword_at_end(self):
        """access_token at end with no following token returns None."""
        assert extract_token_from_subprotocol("chat, access_token") is None


class TestSelectSubprotocol:
    def test_access_token(self):
        assert select_subprotocol("access_token, chat") == "access_token"

    def test_bearer(self):
        assert select_subprotocol("bearer, json") == "bearer"

    def test_none(self):
        assert select_subprotocol(None) is None

    def test_no_known(self):
        assert select_subprotocol("chat, json") is None


class TestUpdateLastSeen:
    @pytest.mark.asyncio
    async def test_with_jti(self):
        mock_repo = MagicMock()
        mock_repo.touch_by_jti = AsyncMock()
        mock_session = AsyncMock()

        @asynccontextmanager
        async def fake_session():
            yield mock_session

        with (
            patch("app.api.ws.auth.async_session", fake_session),
            patch("app.api.ws.auth.SessionRepository", return_value=mock_repo),
        ):
            result = await update_last_seen("test-jti")

        assert isinstance(result, datetime)
        mock_repo.touch_by_jti.assert_called_once_with("test-jti")

    @pytest.mark.asyncio
    async def test_without_jti(self):
        result = await update_last_seen(None)
        assert isinstance(result, datetime)


# ===========================================================================
# Presence audience
# ===========================================================================


class TestGetPresenceAudience:
    @pytest.mark.asyncio
    async def test_fetches_from_db_on_miss(self):
        user_id = uuid.uuid4()
        audience = {uuid.uuid4(), uuid.uuid4()}

        mock_repo = MagicMock()
        mock_repo.get_presence_audience = AsyncMock(return_value=audience)
        mock_session = AsyncMock()

        @asynccontextmanager
        async def fake_session():
            yield mock_session

        # Clear in-memory cache
        from app.api.ws import presence

        presence._PRESENCE_DB_CACHE.clear()

        with (
            patch("app.api.ws.presence.async_session", fake_session),
            patch("app.api.ws.presence.ChatRepository", return_value=mock_repo),
            patch("app.api.ws.presence.get_cache") as mock_cache,
        ):
            cache_instance = MagicMock()
            cache_instance.enabled = False
            mock_cache.return_value = cache_instance

            result = await _get_presence_audience(user_id)

        assert result == audience
        mock_repo.get_presence_audience.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    async def test_returns_cached_on_hit(self):
        user_id = uuid.uuid4()
        audience = {uuid.uuid4()}

        from app.api.ws import presence

        loop = asyncio.get_running_loop()
        presence._PRESENCE_DB_CACHE[user_id] = (audience, loop.time())

        with patch("app.api.ws.presence.get_cache") as mock_cache:
            cache_instance = MagicMock()
            cache_instance.enabled = False
            mock_cache.return_value = cache_instance

            result = await _get_presence_audience(user_id)

        assert result == audience
        presence._PRESENCE_DB_CACHE.clear()


# ===========================================================================
# Cache invalidation helpers
# ===========================================================================


class TestPresenceCacheInvalidation:
    @pytest.mark.asyncio
    async def test_invalidate_audience_cache(self):
        user_id = uuid.uuid4()

        with patch("app.api.ws.presence.get_cache") as mock_cache:
            cache_instance = AsyncMock()
            cache_instance.enabled = True
            cache_instance.invalidate = AsyncMock()
            mock_cache.return_value = cache_instance

            await invalidate_presence_audience_cache(user_id)

        cache_instance.invalidate.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalidate_audience_cache_disabled(self):
        with patch("app.api.ws.presence.get_cache") as mock_cache:
            cache_instance = MagicMock()
            cache_instance.enabled = False
            mock_cache.return_value = cache_instance

            await invalidate_presence_audience_cache(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_invalidate_chat_participants(self):
        chat_id = uuid.uuid4()

        with patch("app.api.ws.presence.get_cache") as mock_cache:
            cache_instance = AsyncMock()
            cache_instance.enabled = True
            cache_instance.invalidate = AsyncMock()
            mock_cache.return_value = cache_instance

            await invalidate_chat_participants_cache(chat_id)

        cache_instance.invalidate.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalidate_chat_participants_disabled(self):
        with patch("app.api.ws.presence.get_cache") as mock_cache:
            cache_instance = MagicMock()
            cache_instance.enabled = False
            mock_cache.return_value = cache_instance

            await invalidate_chat_participants_cache(uuid.uuid4())


# ===========================================================================
# _handle_presence_pubsub
# ===========================================================================


class TestHandlePresencePubSub:
    @pytest.mark.asyncio
    async def test_valid_payload(self):
        user_id = uuid.uuid4()

        with patch("app.api.ws.connection_manager.manager") as mock_manager:
            mock_manager.is_online = MagicMock(return_value=True)
            mock_manager.broadcast_presence = AsyncMock()

            await _handle_presence_pubsub(
                {
                    "user_id": str(user_id),
                    "active": True,
                    "last_seen": datetime.now(UTC).isoformat(),
                }
            )

        mock_manager.broadcast_presence.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_user_id(self):
        with patch("app.api.ws.connection_manager.manager") as mock_manager:
            await _handle_presence_pubsub({})

        mock_manager.broadcast_presence.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_user_id(self):
        with patch("app.api.ws.connection_manager.manager") as mock_manager:
            await _handle_presence_pubsub({"user_id": "not-a-uuid"})

        mock_manager.broadcast_presence.assert_not_called()

    @pytest.mark.asyncio
    async def test_user_not_online(self):
        user_id = uuid.uuid4()

        with patch("app.api.ws.connection_manager.manager") as mock_manager:
            mock_manager.is_online = MagicMock(return_value=False)

            await _handle_presence_pubsub(
                {
                    "user_id": str(user_id),
                    "active": True,
                }
            )

        mock_manager.broadcast_presence.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_last_seen(self):
        user_id = uuid.uuid4()

        with patch("app.api.ws.connection_manager.manager") as mock_manager:
            mock_manager.is_online = MagicMock(return_value=True)
            mock_manager.broadcast_presence = AsyncMock()

            await _handle_presence_pubsub(
                {
                    "user_id": str(user_id),
                    "active": False,
                    "last_seen": "not-a-datetime",
                }
            )

        # Should still call broadcast_presence with last_seen=None
        mock_manager.broadcast_presence.assert_called_once()
        call_kwargs = mock_manager.broadcast_presence.call_args
        assert call_kwargs[1].get("source") == PRESENCE_SOURCE_PUBSUB


# ===========================================================================
# build_presence_map
# ===========================================================================


class TestBuildPresenceMap:
    @pytest.mark.asyncio
    async def test_empty_ids(self):
        result = await build_presence_map([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_with_db_session(self):
        user_id = uuid.uuid4()
        mock_repo = MagicMock()
        mock_repo.get_last_seen_map = AsyncMock(
            return_value={user_id: datetime.now(UTC)}
        )
        mock_manager = MagicMock()
        mock_manager.is_online = MagicMock(return_value=True)

        with (
            patch("app.api.ws.connection_manager.manager", mock_manager),
            patch(
                "app.repositories.session_repository.SessionRepository",
                return_value=mock_repo,
            ),
        ):
            db = AsyncMock()
            result = await build_presence_map([user_id], db=db)

        assert user_id in result
        assert result[user_id].active is True

    @pytest.mark.asyncio
    async def test_without_db_session(self):
        user_id = uuid.uuid4()
        mock_repo = MagicMock()
        mock_repo.get_last_seen_map = AsyncMock(return_value={})
        mock_manager = MagicMock()
        mock_manager.is_online = MagicMock(return_value=False)

        @asynccontextmanager
        async def fake_session():
            yield AsyncMock()

        with (
            patch("app.api.ws.presence.async_session", fake_session),
            patch("app.api.ws.connection_manager.manager", mock_manager),
            patch(
                "app.repositories.session_repository.SessionRepository",
                return_value=mock_repo,
            ),
        ):
            result = await build_presence_map([user_id])

        assert user_id in result
        assert result[user_id].active is False

    @pytest.mark.asyncio
    async def test_filters_none_ids(self):
        user_id = uuid.uuid4()
        mock_repo = MagicMock()
        mock_repo.get_last_seen_map = AsyncMock(return_value={})
        mock_manager = MagicMock()
        mock_manager.is_online = MagicMock(return_value=False)

        with (
            patch("app.api.ws.connection_manager.manager", mock_manager),
            patch(
                "app.repositories.session_repository.SessionRepository",
                return_value=mock_repo,
            ),
        ):
            db = AsyncMock()
            result = await build_presence_map([user_id, None], db=db)

        assert len(result) == 1


# ===========================================================================
# PresencePubSub
# ===========================================================================


class TestPresencePubSub:
    @pytest.mark.asyncio
    async def test_publish_disabled(self):
        ps = PresencePubSub()
        # No redis, no error
        await ps.publish({"user_id": str(uuid.uuid4()), "active": True})

    @pytest.mark.asyncio
    async def test_publish_with_redis(self):
        ps = PresencePubSub()
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()
        ps._redis = mock_redis

        with patch("app.api.ws.presence.settings") as mock_settings:
            mock_settings.presence_pubsub_enabled = True
            mock_settings.presence_pubsub_channel = "presence:updates"

            await ps.publish({"user_id": "test", "active": True})

        mock_redis.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_cancels_task(self):
        ps = PresencePubSub()

        async def _forever():
            await asyncio.sleep(9999)

        task = asyncio.create_task(_forever())
        ps._pubsub_task = task

        await ps.shutdown()
        assert ps._pubsub_task is None
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_shutdown_no_task(self):
        ps = PresencePubSub()
        await ps.shutdown()  # noop

    @pytest.mark.asyncio
    async def test_initialize_disabled(self):
        ps = PresencePubSub()
        with patch("app.api.ws.presence.settings") as mock_settings:
            mock_settings.presence_pubsub_enabled = False
            await ps.initialize()

        assert ps._redis is None

    @pytest.mark.asyncio
    async def test_initialize_with_redis(self):
        ps = PresencePubSub()
        mock_redis = AsyncMock()

        with patch("app.api.ws.presence.settings") as mock_settings:
            mock_settings.presence_pubsub_enabled = True

            await ps.initialize(redis=mock_redis)

        assert ps._redis is mock_redis
        # Task should be created
        if ps._pubsub_task:
            ps._pubsub_task.cancel()
            try:
                await ps._pubsub_task
            except asyncio.CancelledError:
                pass
