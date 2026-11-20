"""Story list cache must not resurrect an in-flight pre-commit snapshot."""

import asyncio
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.auth.security import get_password_hash
from app.core.database import async_session
from app.models import Story
from app.services.story_service import StoryService
from tests.test_stories_api import _login


def _age_memory_entries(cache, seconds, keys=None):
    """Advance only selected cache entries without changing the process clock."""
    from dataclasses import replace

    for key, (entry, expires_at) in list(cache._entries.items()):
        if keys is None or key in keys:
            cache._entries[key] = (
                replace(entry, stored_at=entry.stored_at - seconds),
                expires_at - seconds if expires_at else 0,
            )


async def test_story_create_invalidates_inflight_older_list_snapshot(
    async_client, user_factory, fake_cache, monkeypatch
):
    password = secrets.token_urlsafe(24) + "Aa1!"
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(password)
    )
    headers = await _login(async_client, admin.email, password)

    snapshot_ready = asyncio.Event()
    release_snapshot = asyncio.Event()
    original_list = StoryService.list_active_stories

    async def delayed_first_list(service, locale=None):
        result = await original_list(service, locale)
        if not snapshot_ready.is_set():
            snapshot_ready.set()
            await release_snapshot.wait()
        return result

    monkeypatch.setattr(StoryService, "list_active_stories", delayed_first_list)
    request_headers = {
        "Accept-Language": "ru",
        "X-Query-Budget": "15",
    }
    old_request = asyncio.create_task(
        async_client.get("/stories", headers=request_headers)
    )
    try:
        await asyncio.wait_for(snapshot_ready.wait(), timeout=5)
        now = datetime.now(UTC)
        created = await async_client.post(
            "/stories",
            headers=headers,
            json={
                "title": "Story created during list",
                "short_text": "A committed story",
                "published_at": (now - timedelta(minutes=1)).isoformat(),
                "expires_at": (now + timedelta(days=1)).isoformat(),
                "is_active": True,
            },
        )
        assert created.status_code == 200
        story_id = created.json()["id"]
        async with async_session() as observer:
            assert await observer.get(Story, uuid.UUID(story_id)) is not None
    finally:
        release_snapshot.set()
        old_response = await asyncio.wait_for(old_request, timeout=5)

    assert old_response.status_code == 200
    assert all(row["id"] != story_id for row in old_response.json())
    old_etag = old_response.headers["ETag"]

    fresh = await async_client.get(
        "/stories", headers={**request_headers, "If-None-Match": old_etag}
    )
    assert fresh.status_code == 200
    assert any(row["id"] == story_id for row in fresh.json())
    assert fresh.headers["ETag"] != old_etag
    unchanged = await async_client.get(
        "/stories",
        headers={**request_headers, "If-None-Match": fresh.headers["ETag"]},
    )
    assert unchanged.status_code == 304


async def test_story_generation_is_shared_but_not_served_from_worker_l1():
    from app.api.stories import stories_version_resolver as resolver
    from app.deps.cache import MemoryCache, TieredCache

    shared = MemoryCache(default_ttl=600)
    writer = TieredCache(MemoryCache(default_ttl=600), shared)
    reader = TieredCache(MemoryCache(default_ttl=600), shared)
    old = await resolver.get_version(reader)
    old_key = f"ue:stories:list:{old}:ru:request"
    await reader.set(old_key, [{"title": "old"}])
    assert await reader.l1.get(old_key) is not None

    await resolver.increment(writer)

    new = await resolver.get_version(reader)
    assert new != old
    assert await reader.get(f"ue:stories:list:{new}:ru:request") is None
    assert await reader.l1.get(old_key) is not None


async def test_story_generation_expiry_cannot_resurrect_an_old_payload():
    from app.api.stories import stories_version_resolver as resolver
    from app.deps.cache import MemoryCache

    cache = MemoryCache(default_ttl=600)
    old = await resolver.get_version(cache)
    assert await resolver.get_version(cache) == old
    old_key = f"ue:stories:list:{old}:ru:request"
    await cache.set(old_key, [{"title": "old"}], ttl=600)

    _age_memory_entries(cache, 301)

    assert await cache.get(old_key) is not None
    new = await resolver.get_version(cache)
    assert new != old
    assert await cache.get(f"ue:stories:list:{new}:ru:request") is None


async def test_story_generation_disabled_and_unavailable_backends():
    import time

    from app.api.stories import stories_version_resolver as resolver
    from app.deps.cache import CacheEntry, MemoryCache, NullCache

    disabled = NullCache()
    assert await resolver.get_version(disabled) == "0"
    await resolver.increment(disabled)

    class Unavailable(MemoryCache):
        async def get(self, key):
            return None

        async def set(self, key, payload, ttl=None):
            return CacheEntry(payload=payload, etag="", stored_at=time.time())

    unavailable = Unavailable()
    assert await resolver.get_version(unavailable) != await resolver.get_version(
        unavailable
    )


async def test_story_initial_reader_miss_cannot_publish_an_old_snapshot():
    from app.api.stories import stories_version_resolver as resolver
    from app.deps.cache import MemoryCache

    first_miss = asyncio.Event()
    release_miss = asyncio.Event()

    class DelayedCache(MemoryCache):
        async def get(self, key):
            value = await super().get(key)
            if value is None and not first_miss.is_set():
                first_miss.set()
                await release_miss.wait()
            return value

    cache = DelayedCache()
    committed = []

    async def reader():
        version = await resolver.get_version(cache)
        snapshot = list(committed)
        await cache.set(f"ue:stories:list:{version}:ru:request", snapshot)
        return version

    first_reader = asyncio.create_task(reader())
    try:
        await asyncio.wait_for(first_miss.wait(), timeout=5)
        committed.append("created")
        await resolver.increment(cache)
        writer_version = await resolver.get_version(cache)
    finally:
        release_miss.set()
        reader_version = await asyncio.wait_for(first_reader, timeout=5)

    assert reader_version != writer_version
    assert await resolver.get_version(cache) == reader_version
    entry = await cache.get(f"ue:stories:list:{reader_version}:ru:request")
    assert entry is not None and entry.payload == ["created"]


async def test_story_cache_keeps_tenant_payloads_separate(monkeypatch):
    import json
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi import Request, Response

    from app.api import stories
    from app.core.tenant import get_current_tenant, set_current_tenant, tenant_id_ctx
    from app.deps import cache as cache_module
    from app.deps.cache import MemoryCache
    from tests.conftest import call_injected

    monkeypatch.setattr(cache_module, "_cache_backend", MemoryCache(default_ttl=600))
    service = SimpleNamespace(
        list_active_stories=AsyncMock(
            side_effect=lambda locale: [{"tenant": get_current_tenant()}]
        )
    )

    async def list_for(tenant):
        token = set_current_tenant(tenant)
        try:
            request = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/stories",
                    "query_string": b"",
                    "headers": [],
                }
            )
            result = await call_injected(
                stories.list_stories,
                request=request,
                response=Response(),
                if_none_match=None,
                provides={"StoryService": service},
            )
            return json.loads(result.body) if isinstance(result, Response) else result
        finally:
            tenant_id_ctx.reset(token)

    assert await list_for("tenant-a") == [{"tenant": "tenant-a"}]
    assert await list_for("tenant-b") == [{"tenant": "tenant-b"}]
    assert await list_for("tenant-a") == [{"tenant": "tenant-a"}]
    assert service.list_active_stories.await_count == 2


@pytest.mark.parametrize("operation", ["update", "delete"])
async def test_story_mutations_refresh_etags(
    async_client, user_factory, story_factory, fake_cache, operation
):
    from app.api.stories import stories_version_resolver

    password = secrets.token_urlsafe(24) + "Aa1!"
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(password)
    )
    headers = await _login(async_client, admin.email, password)
    story = await story_factory(title="Before", short_text="Body")

    initial = await async_client.get("/stories", headers={"Accept-Language": "ru"})
    assert initial.status_code == 200
    assert any(row["id"] == str(story.id) for row in initial.json())
    old_etag = initial.headers["ETag"]
    old_version = await stories_version_resolver.get_version(fake_cache)

    if operation == "update":
        result = await async_client.patch(
            f"/stories/{story.id}", headers=headers, json={"title": "After"}
        )
    else:
        result = await async_client.delete(f"/stories/{story.id}", headers=headers)
    assert result.status_code == 200
    assert await stories_version_resolver.get_version(fake_cache) != old_version

    updated = await async_client.get(
        "/stories", headers={"Accept-Language": "ru", "If-None-Match": old_etag}
    )
    assert updated.status_code == 200
    rows = [row for row in updated.json() if row["id"] == str(story.id)]
    assert [row["title"] for row in rows] == (
        ["After"] if operation == "update" else []
    )
    assert updated.headers["ETag"] != old_etag
    unchanged = await async_client.get(
        "/stories",
        headers={"Accept-Language": "ru", "If-None-Match": updated.headers["ETag"]},
    )
    assert unchanged.status_code == 304


@pytest.mark.parametrize(
    "cache_control", ["no-cache, no-store", "no-cache", "no-store"]
)
@pytest.mark.parametrize("default_ttl", [0, 300])
async def test_admin_revalidation_reads_after_cache_outage(
    async_client, user_factory, fake_cache, monkeypatch, cache_control, default_ttl
):
    import time

    import app.core.lifespan as lifespan_module
    from app.core.cache_versioning import STORIES_GENERATION_KEY
    from app.core.config import settings
    from app.deps import cache as cache_module
    from app.deps.cache import CacheEntry, MemoryCache

    actual_wall_clock = time.time
    original_shutdown = lifespan_module._shutdown_subsystems

    async def shutdown_without_global_clock_change(app):
        try:
            assert time.time is actual_wall_clock
        finally:
            await original_shutdown(app)

    monkeypatch.setattr(
        lifespan_module, "_shutdown_subsystems", shutdown_without_global_clock_change
    )
    password = secrets.token_urlsafe(24) + "Aa1!"
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(password)
    )
    headers = await _login(async_client, admin.email, password)
    with monkeypatch.context() as cache_scope:
        cache_scope.setattr(settings, "cache_default_ttl_seconds", default_ttl)
        cache = MemoryCache(default_ttl=default_ttl)
        cache_scope.setattr(cache_module, "_cache_backend", cache)
        initial = await async_client.get("/stories", headers={"Accept-Language": "ru"})
        assert initial.status_code == 200
        assert initial.json() == []
        old_etag = initial.headers["ETag"]
        payload_keys = [
            key for key in cache._entries if key.startswith("ue:stories:list:")
        ]
        assert len(payload_keys) == 1
        payload_key = payload_keys[0]
        for key in (STORIES_GENERATION_KEY, payload_key):
            entry, expires_at = cache._entries[key]
            assert entry.ttl_seconds == 300
            assert expires_at > entry.stored_at

        async def dropped_invalidation(*keys):
            return None

        async def dropped_set(key, payload, ttl=None):
            return CacheEntry(payload=payload, etag="", stored_at=0)

        # RedisCache logs and returns on transport errors. Simulate the same
        # loss while retaining its previously cached entry for the recovery.
        with monkeypatch.context() as outage:
            outage.setattr(cache, "invalidate", dropped_invalidation)
            outage.setattr(cache, "set", dropped_set)
            now = datetime.now(UTC)
            created = await async_client.post(
                "/stories",
                headers=headers,
                json={
                    "title": "Created during outage",
                    "short_text": "Committed",
                    "published_at": (now - timedelta(minutes=1)).isoformat(),
                    "expires_at": (now + timedelta(days=1)).isoformat(),
                    "is_active": True,
                },
            )
            assert created.status_code == 200
            story_id = created.json()["id"]
            async with async_session() as observer:
                assert await observer.get(Story, uuid.UUID(story_id)) is not None

        ordinary = await async_client.get("/stories", headers={"Accept-Language": "ru"})
        assert ordinary.status_code == 200
        assert ordinary.json() == []

        revalidated = await async_client.get(
            "/stories",
            headers={
                "Accept-Language": "ru",
                "Cache-Control": cache_control,
                "If-None-Match": old_etag,
            },
        )
        assert revalidated.status_code == 200
        assert any(row["id"] == story_id for row in revalidated.json())
        assert revalidated.headers["ETag"] != old_etag

        unchanged = await async_client.get(
            "/stories",
            headers={
                "Accept-Language": "ru",
                "Cache-Control": cache_control,
                "If-None-Match": revalidated.headers["ETag"],
            },
        )
        assert unchanged.status_code == 304
        ordinary_after = await async_client.get(
            "/stories", headers={"Accept-Language": "ru"}
        )
        assert ordinary_after.status_code == 200
        assert ordinary_after.json() == []

        # Age only these stored entries. This exercises their configured TTLs
        # while leaving the process clock untouched during the request and shutdown.
        _age_memory_entries(cache, 301, {STORIES_GENERATION_KEY, payload_key})
        assert await cache.get(STORIES_GENERATION_KEY) is None
        assert await cache.get(payload_key) is None
        original_list = StoryService.list_active_stories

        async def list_without_global_clock_change(service, locale):
            assert time.time is actual_wall_clock
            return await original_list(service, locale)

        with monkeypatch.context() as request_guard:
            request_guard.setattr(
                StoryService, "list_active_stories", list_without_global_clock_change
            )
            after_expiry = await async_client.get(
                "/stories", headers={"Accept-Language": "ru"}
            )
        assert time.time is actual_wall_clock
        assert after_expiry.status_code == 200
        assert any(row["id"] == story_id for row in after_expiry.json())

    assert cache_module.get_cache() is fake_cache
    assert await (await fake_cache._get_client()).ping()


@pytest.mark.parametrize(
    ("default_ttl", "l1_ttl", "expected"),
    [
        (0, None, 300),
        (600, None, 300),
        (60, None, 60),
        (600, 20, 20),
        (0, 0, 300),
    ],
)
async def test_story_payload_cache_has_finite_ttl(
    monkeypatch, default_ttl, l1_ttl, expected
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi import Request, Response

    from app.api.deps.etag import cached_endpoint, generate_cache_key
    from app.core.config import settings
    from app.core.tenant import get_current_tenant
    from app.deps import cache as cache_module
    from app.deps.cache import MemoryCache, TieredCache

    monkeypatch.setattr(settings, "cache_default_ttl_seconds", default_ttl)
    cache = MemoryCache(default_ttl=default_ttl)
    if l1_ttl is not None:
        monkeypatch.setattr(settings, "cache_l1_ttl_seconds", l1_ttl)
        cache = TieredCache(MemoryCache(default_ttl=l1_ttl), cache)
    monkeypatch.setattr(cache_module, "_cache_backend", cache)

    @cached_endpoint(
        SimpleNamespace(get_version=AsyncMock(return_value="current")),
        "stories-test",
        max_cache_ttl_seconds=300,
    )
    async def endpoint(**kwargs):
        return [{"title": "cached"}]

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/stories",
            "query_string": b"",
            "headers": [(b"accept-language", b"ru")],
        }
    )
    await endpoint(request=request, response=Response())
    key = generate_cache_key(
        "stories-test", "current", "ru", {"__tenant_id": get_current_tenant()}
    )
    entry = await cache.get(key)
    assert entry is not None and entry.ttl_seconds == expected


async def test_story_revalidation_preserves_etag_for_unchanged_payload(
    async_client, story_factory, fake_cache
):
    await story_factory(title="ETag stable", short_text="Unchanged")
    initial = await async_client.get("/stories", headers={"Accept-Language": "ru"})
    assert initial.status_code == 200
    response = await async_client.get(
        "/stories",
        headers={
            "Accept-Language": "ru",
            "Cache-Control": "no-cache, no-store",
            "If-None-Match": initial.headers["ETag"],
        },
    )
    assert response.status_code == 304
    assert response.headers["ETag"] == initial.headers["ETag"]


async def test_story_revalidation_etag_is_stable_without_cache(
    async_client, story_factory, monkeypatch
):
    from app.deps import cache as cache_module
    from app.deps.cache import NullCache

    monkeypatch.setattr(cache_module, "_cache_backend", NullCache())
    await story_factory(title="ETag without cache", short_text="Unchanged")
    initial = await async_client.get("/stories", headers={"Accept-Language": "ru"})
    assert initial.status_code == 200
    response = await async_client.get(
        "/stories",
        headers={
            "Accept-Language": "ru",
            "Cache-Control": "no-cache",
            "If-None-Match": initial.headers["ETag"],
        },
    )
    assert response.status_code == 304
    assert response.headers["ETag"] == initial.headers["ETag"]


@pytest.mark.parametrize(
    ("bucket_ttl", "can_cache"),
    [(None, False), (0, False), (301, False), (60, True), (300, True)],
)
@pytest.mark.parametrize("tiered", [False, True])
async def test_stories_nats_requires_bounded_bucket_retention(
    monkeypatch, bucket_ttl, can_cache, tiered
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi import Request, Response
    from nats.js.errors import KeyNotFoundError

    from app.api import stories
    from app.core.config import settings
    from app.deps import cache as cache_module
    from app.deps.cache import MemoryCache, NatsKVCache, TieredCache, _decode_kv_key
    from tests.conftest import call_injected

    monkeypatch.setattr(settings, "cache_default_ttl_seconds", 60)

    class Bucket:
        def __init__(self):
            self.values = {}

        async def status(self):
            return SimpleNamespace(ttl=bucket_ttl)

        async def get(self, key):
            if key not in self.values:
                raise KeyNotFoundError
            return SimpleNamespace(value=self.values[key])

        async def put(self, key, value):
            self.values[key] = value

    bucket = Bucket()
    nats_cache = NatsKVCache(bucket="test", default_ttl=300)
    nats_cache._kv = bucket
    cache = TieredCache(MemoryCache(), nats_cache) if tiered else nats_cache
    monkeypatch.setattr(cache_module, "_cache_backend", cache)
    service = SimpleNamespace(
        list_active_stories=AsyncMock(return_value=[{"title": "example"}])
    )

    async def read():
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/stories",
                "query_string": b"",
                "headers": [],
            }
        )
        return await call_injected(
            stories.list_stories,
            request=request,
            response=Response(),
            if_none_match=None,
            provides={"StoryService": service},
        )

    await read()
    await read()
    assert service.list_active_stories.await_count == (1 if can_cache else 2)
    assert bool(bucket.values) is can_cache
    if can_cache:
        # The fake retains entries to exercise the requested TTL independently
        # of the bucket-wide retention advertised by status().
        import json

        for key, raw in list(bucket.values.items()):
            if _decode_kv_key(key).startswith("ue:stories:list:"):
                entry = json.loads(raw)
                entry["stored_at"] -= 61
                bucket.values[key] = json.dumps(entry).encode()
        if tiered:
            _age_memory_entries(cache.l1, 61)
        await read()
        assert service.list_active_stories.await_count == 2
    await stories.stories_version_resolver.increment(cache)
    assert bool(bucket.values) is can_cache


def test_bounded_endpoint_rejects_nonpositive_ttl():
    from app.api.deps.etag import cached_endpoint

    with pytest.raises(ValueError, match="Maximum cache TTL must be positive"):
        cached_endpoint(None, "invalid", max_cache_ttl_seconds=0)


@pytest.mark.parametrize("failure", ["nats", "os", "unavailable"])
async def test_stories_nats_status_failure_bypasses_cache(failure):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from nats.errors import Error as NatsError

    from app.api.stories import stories_version_resolver as resolver
    from app.deps.cache import CacheBackendUnavailable, NatsKVCache

    failures = {
        "nats": NatsError(),
        "os": OSError(),
        "unavailable": CacheBackendUnavailable(),
    }
    status = AsyncMock(side_effect=failures[failure])
    put = AsyncMock()
    cache = NatsKVCache(bucket="test", default_ttl=300)
    cache._kv = SimpleNamespace(status=status, put=put)
    assert not await resolver.cache_allowed(cache)
    await resolver.increment(cache)
    put.assert_not_awaited()


async def test_story_generation_does_not_write_to_disabled_tiers():
    from app.api.stories import stories_version_resolver as resolver
    from app.deps.cache import NullCache, TieredCache

    cache = TieredCache(NullCache(), NullCache())
    await resolver.increment(cache)
    assert await resolver.get_version(cache) == "0"


async def test_no_cache_request_is_opt_in_for_other_cached_endpoints(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi import Request, Response

    from app.api.deps.etag import cached_endpoint
    from app.deps import cache as cache_module
    from app.deps.cache import MemoryCache

    monkeypatch.setattr(cache_module, "_cache_backend", MemoryCache(default_ttl=300))
    calls = 0

    @cached_endpoint(SimpleNamespace(get_version=AsyncMock(return_value="1")), "other")
    async def endpoint(**kwargs):
        nonlocal calls
        calls += 1
        return {"calls": calls}

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/other",
            "query_string": b"",
            "headers": [(b"cache-control", b"no-cache")],
        }
    )
    await endpoint(request=request, response=Response())
    cached = await endpoint(request=request, response=Response())
    assert cached == {"calls": 1}
    assert calls == 1


async def test_story_redis_ttl_and_revalidation_with_zero_default(
    fake_cache, monkeypatch
):
    import json
    import time
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi import Request, Response

    from app.api import stories
    from app.core.cache_versioning import STORIES_GENERATION_KEY
    from app.core.config import settings
    from app.deps import cache as cache_module
    from tests.conftest import call_injected
    from tests.fixtures.services.service_fixtures import _TestingRedisCache

    actual_wall_clock = time.time
    cache = _TestingRedisCache(url=settings.cache_redis_url, default_ttl=0)
    cache._client = await fake_cache._get_client()
    with monkeypatch.context() as cache_scope:
        cache_scope.setattr(settings, "cache_default_ttl_seconds", 0)
        cache_scope.setattr(cache_module, "_cache_backend", cache)
        payload = [{"title": "old"}]

        async def list_without_global_clock_change(locale):
            assert time.time is actual_wall_clock
            return list(payload)

        service = SimpleNamespace(
            list_active_stories=AsyncMock(side_effect=list_without_global_clock_change)
        )

        async def read(*, cache_control=None, etag=None):
            headers = []
            if cache_control is not None:
                headers.append((b"cache-control", cache_control.encode()))
            if etag is not None:
                headers.append((b"if-none-match", etag.encode()))
            request = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/stories",
                    "query_string": b"",
                    "headers": headers,
                }
            )
            return await call_injected(
                stories.list_stories,
                request=request,
                response=Response(),
                if_none_match=None,
                provides={"StoryService": service},
            )

        first = await read()
        assert first.status_code == 200
        old_etag = first.headers["ETag"]
        redis = await cache._get_client()
        keys = await redis.keys("ue:stories:list:*")
        assert len(keys) == 1
        for key in (STORIES_GENERATION_KEY, keys[0]):
            entry = await cache.get(key)
            assert entry is not None and entry.ttl_seconds == 300
            assert 0 < await redis.ttl(key) <= 300

        # An outage can lose invalidation, leaving the old Redis entry in place.
        payload.append({"title": "created"})
        assert await read() == [{"title": "old"}]
        fresh = await read(cache_control="no-cache", etag=old_etag)
        assert fresh.status_code == 200
        assert json.loads(fresh.body) == payload
        assert fresh.headers["ETag"] != old_etag
        unchanged = await read(cache_control="no-cache", etag=fresh.headers["ETag"])
        assert unchanged.status_code == 304

        # EXPIRE 0 models Redis reaching the already-proven finite deadline, with
        # no process-wide clock patch and no wall-clock sleep.
        for key in (STORIES_GENERATION_KEY, keys[0]):
            assert await redis.expire(key, 0)
            assert not await redis.exists(key)
        recovered = await read()
        assert recovered.status_code == 200
        assert json.loads(recovered.body) == payload
        assert time.time is actual_wall_clock

    assert cache_module.get_cache() is fake_cache
    assert await (await fake_cache._get_client()).ping()
