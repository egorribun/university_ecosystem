"""Absent NATS buckets cannot turn committed story mutations into failures."""

import secrets
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from nats.js.client import JetStreamContext
from nats.js.errors import KeyNotFoundError, NotFoundError
from nats.js.kv import KeyValue
from sqlalchemy import select

from app.auth.security import get_password_hash
from app.core import nats_broker
from app.core.database import async_session
from app.deps import cache as cache_module
from app.deps.cache import NatsKVCache, StrictCacheInvalidationError
from app.models import Story
from tests.test_stories_api import _login


def _missing_stream():
    return NotFoundError(code=404, err_code=10059)


def _cache_with_unavailable_bucket(monkeypatch, case):
    cache = NatsKVCache(bucket="test", default_ttl=300)
    if case == "never_created":
        js = JetStreamContext(conn=None)
        js.stream_info = AsyncMock(side_effect=_missing_stream())
        monkeypatch.setattr(
            nats_broker, "broker", SimpleNamespace(is_connected=True, js=js)
        )
    else:
        js = SimpleNamespace(
            subscribe=AsyncMock(side_effect=_missing_stream()),
            stream_info=AsyncMock(side_effect=_missing_stream()),
        )
        cache._kv = KeyValue(
            name="test", stream="KV_test", pre="$KV.test.", js=js, direct=False
        )
    return cache


@pytest.mark.parametrize("case", ["never_created", "deleted"])
async def test_story_create_succeeds_after_nats_bucket_disappears(
    app, async_client, user_factory, fake_cache, monkeypatch, case
):
    password = secrets.token_urlsafe(24) + "Aa1!"
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(password)
    )
    headers = await _login(async_client, admin.email, password)
    cache = _cache_with_unavailable_bucket(monkeypatch, case)
    monkeypatch.setattr(cache_module, "_cache_backend", cache)
    warning = Mock()
    monkeypatch.setattr(cache_module, "logger", SimpleNamespace(warning=warning))
    title = "Missing NATS bucket " + secrets.token_hex(6)
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
                "short_text": "Body",
                "published_at": (now - timedelta(minutes=1)).isoformat(),
                "expires_at": (now + timedelta(days=1)).isoformat(),
                "is_active": True,
            },
        )
    async with async_session() as observer:
        result = await observer.execute(select(Story).where(Story.title == title))
        assert result.scalar_one_or_none() is not None
    assert response.status_code == 200, "story committed before missing bucket surfaced"
    assert warning.call_args.args == ("NATS KV invalidate failed",)
    assert warning.call_args.kwargs["error_type"] == (
        "BucketNotFoundError" if case == "never_created" else "NotFoundError"
    )


@pytest.mark.parametrize("operation", ["set", "invalidate"])
@pytest.mark.parametrize("case", ["never_created", "deleted"])
async def test_non_strict_cache_handles_only_missing_bucket(
    monkeypatch, operation, case
):
    warning = Mock()
    monkeypatch.setattr(cache_module, "logger", SimpleNamespace(warning=warning))
    if case == "never_created":
        cache = _cache_with_unavailable_bucket(monkeypatch, case)
    else:
        cache = NatsKVCache(bucket="test", default_ttl=60)
        cache._kv = SimpleNamespace(
            keys=AsyncMock(side_effect=_missing_stream()),
            put=AsyncMock(side_effect=_missing_stream()),
        )
    if operation == "set":
        entry = await cache.set("item", {"value": 1}, ttl=60)
        assert entry.payload == {"value": 1} and entry.etag
    else:
        await cache.invalidate("item:*")
    assert warning.call_args.kwargs["error_type"] == (
        "BucketNotFoundError" if case == "never_created" else "NotFoundError"
    )


@pytest.mark.parametrize("operation", ["set", "invalidate"])
@pytest.mark.parametrize(
    "error",
    [
        NotFoundError(code=404, err_code=10014),
        NotFoundError(code=404, err_code=None),
        NotFoundError(code=500, err_code=10059),
        KeyNotFoundError(),
    ],
)
async def test_unrelated_nats_not_found_errors_propagate(operation, error):
    bucket = SimpleNamespace(
        keys=AsyncMock(side_effect=error),
        put=AsyncMock(side_effect=error),
    )
    cache = NatsKVCache(bucket="test", default_ttl=60)
    cache._kv = bucket
    with pytest.raises(type(error)):
        if operation == "set":
            await cache.set("item", {"value": 1})
        else:
            await cache.invalidate("item:*")


@pytest.mark.parametrize("case", ["never_created", "deleted"])
async def test_strict_invalidation_fails_closed_for_missing_bucket(monkeypatch, case):
    if case == "never_created":
        cache = _cache_with_unavailable_bucket(monkeypatch, case)
    else:
        cache = NatsKVCache(bucket="test", default_ttl=60)
        cache._kv = SimpleNamespace(delete=AsyncMock(side_effect=_missing_stream()))
    with pytest.raises(StrictCacheInvalidationError):
        await cache.invalidate_strict("item")


@pytest.mark.parametrize("case", ["never_created", "deleted"])
async def test_nats_bucket_recovery_resumes_finite_generation_writes(monkeypatch, case):
    import json

    from app.core.cache_versioning import StoriesVersionResolver

    warning = Mock()
    monkeypatch.setattr(cache_module, "logger", SimpleNamespace(warning=warning))
    cache = _cache_with_unavailable_bucket(monkeypatch, case)
    await cache.invalidate("ue:stories:list:*")
    assert warning.called
    if case == "never_created":
        assert cache._kv is None
        js = nats_broker.broker.js
        js.stream_info.side_effect = None
    else:
        js = cache._kv._js
        js.stream_info.side_effect = None
    js.stream_info.return_value = SimpleNamespace(
        config=SimpleNamespace(max_msgs_per_subject=1, allow_direct=False, max_age=60)
    )
    js.publish = AsyncMock(return_value=SimpleNamespace(seq=1))
    resolver = StoriesVersionResolver()
    assert await resolver.cache_allowed(cache)
    await resolver.increment(cache)
    assert json.loads(js.publish.await_args.args[1])["ttl_seconds"] == 300
