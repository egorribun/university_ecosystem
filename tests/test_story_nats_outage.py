"""Committed story writes must survive cache transport failures."""

import secrets
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from nats.errors import (
    ConnectionClosedError,
    ConnectionDrainingError,
    ConnectionReconnectingError,
    NoRespondersError,
    NoServersError,
    OutboundBufferLimitError,
    StaleConnectionError,
)
from nats.js.errors import (
    InvalidKeyError,
    NoKeysError,
    NoStreamResponseError,
    ServerError,
    ServiceUnavailableError,
)
from sqlalchemy import select

from app.auth.security import get_password_hash
from app.core.database import async_session
from app.deps import cache as cache_module
from app.deps.cache import CacheBackendUnavailable, NatsKVCache
from app.models import Story
from tests.test_stories_api import _login


async def test_committed_story_create_succeeds_when_nats_invalidation_disconnects(
    app, async_client, user_factory, fake_cache, monkeypatch
):
    password = secrets.token_urlsafe(24) + "Aa1!"
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(password)
    )
    headers = await _login(async_client, admin.email, password)
    bucket = SimpleNamespace(
        keys=AsyncMock(side_effect=ConnectionClosedError()),
        status=AsyncMock(side_effect=ConnectionClosedError()),
    )
    cache = NatsKVCache(bucket="test", default_ttl=300)
    cache._kv = bucket
    monkeypatch.setattr(cache_module, "_cache_backend", cache)
    title = "Closed NATS during committed story creation"
    now = datetime.now(UTC)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver/api/v1",
    ) as client:
        response = await client.post(
            "/stories",
            headers=headers,
            json={
                "title": title,
                "short_text": "Committed story",
                "published_at": (now - timedelta(minutes=1)).isoformat(),
                "expires_at": (now + timedelta(days=1)).isoformat(),
                "is_active": True,
            },
        )
    async with async_session() as observer:
        result = await observer.execute(select(Story).where(Story.title == title))
        assert result.scalar_one_or_none() is not None
    assert response.status_code == 200, "story committed before cache failure"


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
@pytest.mark.parametrize("failure_point", ["invalidation", "generation"])
async def test_story_mutations_survive_nats_transport_loss(
    app,
    async_client,
    user_factory,
    story_factory,
    fake_cache,
    monkeypatch,
    operation,
    failure_point,
):
    from unittest.mock import Mock

    from app.core.cache_versioning import STORIES_GENERATION_KEY
    from app.deps.cache import _encode_kv_key

    password = secrets.token_urlsafe(24) + "Aa1!"
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(password)
    )
    headers = await _login(async_client, admin.email, password)
    story = None if operation == "create" else await story_factory(title="Before")
    warning = Mock()
    monkeypatch.setattr(cache_module, "logger", SimpleNamespace(warning=warning))
    bucket = SimpleNamespace(
        keys=AsyncMock(return_value=[]),
        delete=AsyncMock(),
        status=AsyncMock(return_value=SimpleNamespace(ttl=60)),
        put=AsyncMock(),
    )
    if failure_point == "invalidation":
        bucket.keys.side_effect = ConnectionClosedError()
    else:
        bucket.put.side_effect = ConnectionClosedError()
    cache = NatsKVCache(bucket="test", default_ttl=300)
    cache._kv = bucket
    monkeypatch.setattr(cache_module, "_cache_backend", cache)
    now = datetime.now(UTC)
    title = "NATS failure story " + secrets.token_hex(6)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver/api/v1",
    ) as client:
        if operation == "create":
            response = await client.post(
                "/stories",
                headers=headers,
                json={
                    "title": title,
                    "short_text": "Body",
                    "published_at": (now - timedelta(minutes=1)).isoformat(),
                    "expires_at": (now + timedelta(days=1)).isoformat(),
                    "is_active": True,
                },
            )
        elif operation == "update":
            response = await client.patch(
                f"/stories/{story.id}", headers=headers, json={"title": title}
            )
        else:
            response = await client.delete(f"/stories/{story.id}", headers=headers)
    async with async_session() as observer:
        if operation == "create":
            result = await observer.execute(select(Story).where(Story.title == title))
            assert result.scalar_one_or_none() is not None
        else:
            row = await observer.get(Story, story.id)
            assert (row is None) if operation == "delete" else row.title == title
    assert response.status_code == 200
    message = (
        "NATS KV invalidate failed"
        if failure_point == "invalidation"
        else "NATS KV set failed"
    )
    assert warning.call_args.args == (message,)
    assert warning.call_args.kwargs["error_type"] == "ConnectionClosedError"
    if failure_point == "invalidation":
        # The shared generation is still rotated if the transport recovers
        # before the following write; its metadata retains the finite cap.
        import json

        assert bucket.put.await_args.args[0] == _encode_kv_key(STORIES_GENERATION_KEY)
        assert json.loads(bucket.put.await_args.args[1])["ttl_seconds"] == 300


@pytest.mark.parametrize("operation", ["set", "invalidate"])
@pytest.mark.parametrize(
    "failure_type",
    [
        ConnectionClosedError,
        ConnectionReconnectingError,
        ConnectionDrainingError,
        NoServersError,
        NoRespondersError,
        OutboundBufferLimitError,
        StaleConnectionError,
        ServiceUnavailableError,
        ServerError,
        NoStreamResponseError,
        CacheBackendUnavailable,
        OSError,
    ],
)
async def test_nats_cache_transport_failures_are_reported_and_fail_open(
    monkeypatch, operation, failure_type
):
    from unittest.mock import Mock

    warning = Mock()
    monkeypatch.setattr(cache_module, "logger", SimpleNamespace(warning=warning))
    bucket = SimpleNamespace(put=AsyncMock(), keys=AsyncMock())
    if operation == "set":
        bucket.put.side_effect = failure_type()
    else:
        bucket.keys.side_effect = failure_type()
    cache = NatsKVCache(bucket="test", default_ttl=60)
    cache._kv = bucket
    if operation == "set":
        entry = await cache.set("item", {"value": 1})
        assert entry.payload == {"value": 1}
        assert entry.etag
    else:
        await cache.invalidate("item:*")
    assert warning.call_args.kwargs["error_type"] == failure_type.__name__


@pytest.mark.parametrize("operation", ["set", "invalidate"])
@pytest.mark.parametrize("failure_type", [RuntimeError, InvalidKeyError, NoKeysError])
async def test_nats_cache_unexpected_errors_are_not_swallowed(operation, failure_type):
    bucket = SimpleNamespace(put=AsyncMock(), keys=AsyncMock(), delete=AsyncMock())
    if operation == "set":
        bucket.put.side_effect = failure_type()
    else:
        bucket.keys.return_value = ["item=3a1"]
        bucket.delete.side_effect = failure_type()
    cache = NatsKVCache(bucket="test", default_ttl=60)
    cache._kv = bucket
    with pytest.raises(failure_type):
        if operation == "set":
            await cache.set("item", {"value": 1})
        else:
            await cache.invalidate("item:*")


async def test_healthy_story_create_invalidates_nats_and_rotates_generation(
    async_client, user_factory, fake_cache, monkeypatch
):
    from app.api.stories import stories_version_resolver as resolver
    from app.core.cache_versioning import STORIES_GENERATION_KEY
    from tests.test_nats_kv_cache import _GrammarCheckedKV

    class Bucket(_GrammarCheckedKV):
        async def status(self):
            return SimpleNamespace(ttl=60)

    password = secrets.token_urlsafe(24) + "Aa1!"
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(password)
    )
    headers = await _login(async_client, admin.email, password)
    bucket = Bucket()
    cache = NatsKVCache(bucket="test", default_ttl=300)
    cache._kv = bucket
    monkeypatch.setattr(cache_module, "_cache_backend", cache)
    old_generation = await resolver.get_version(cache)
    old_key = f"ue:stories:list:{old_generation}:ru:example"
    await cache.set(old_key, [{"title": "stale"}], ttl=300)
    now = datetime.now(UTC)
    response = await async_client.post(
        "/stories",
        headers=headers,
        json={
            "title": "Healthy NATS story",
            "short_text": "Body",
            "published_at": (now - timedelta(minutes=1)).isoformat(),
            "expires_at": (now + timedelta(days=1)).isoformat(),
            "is_active": True,
        },
    )
    assert response.status_code == 200
    assert await cache.get(old_key) is None
    assert await resolver.get_version(cache) != old_generation
    generation = await cache.get(STORIES_GENERATION_KEY)
    assert generation is not None and generation.ttl_seconds == 300
