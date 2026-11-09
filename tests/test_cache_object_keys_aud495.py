from __future__ import annotations

import secrets
from typing import ClassVar
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import RedisError

from app.deps.cache import (
    MemoryCache,
    NatsKVCache,
    RedisCache,
    RedisClusterCache,
    cached,
)


@pytest.mark.asyncio
async def test_default_key_keeps_bound_receiver_and_preserves_same_instance_hits() -> (
    None
):
    class TenantService:
        def __init__(self, tenant: str) -> None:
            self.tenant = tenant
            self.calls = 0

        @cached(prefix="aud495-instance")
        async def load(self, item_id: str) -> str:
            self.calls += 1
            return f"{self.tenant}:{item_id}"

    cache = MemoryCache()
    first = TenantService("tenant-a")
    second = TenantService("tenant-b")
    with patch("app.deps.cache.get_cache", return_value=cache):
        assert await first.load("same-item") == "tenant-a:same-item"
        assert await first.load("same-item") == "tenant-a:same-item"
        assert await second.load("same-item") == "tenant-b:same-item"

    assert first.calls == 1
    assert second.calls == 1


@pytest.mark.asyncio
async def test_default_key_keeps_classmethod_receiver_per_class() -> None:
    class Loader:
        calls: ClassVar[dict[type[Loader], int]] = {}

        @classmethod
        @cached(prefix="aud495-classmethod")
        async def load(cls, item_id: str) -> str:
            cls.calls[cls] = cls.calls.get(cls, 0) + 1
            return f"{cls.__name__}:{item_id}"

    class ChildLoader(Loader):
        pass

    cache = MemoryCache()
    with patch("app.deps.cache.get_cache", return_value=cache):
        assert await Loader.load("same-item") == "Loader:same-item"
        assert await Loader.load("same-item") == "Loader:same-item"
        assert await ChildLoader.load("same-item") == "ChildLoader:same-item"

    assert Loader.calls == {Loader: 1, ChildLoader: 1}


@pytest.mark.asyncio
async def test_default_key_keeps_first_argument_for_free_function() -> None:
    class Tenant:
        def __init__(self, name: str) -> None:
            self.name = name

    @cached(prefix="aud495-free")
    async def load(tenant: Tenant, item_id: str) -> str:
        return f"{tenant.name}:{item_id}"

    cache = MemoryCache()
    with patch("app.deps.cache.get_cache", return_value=cache):
        assert await load(Tenant("tenant-a"), "same-item") == "tenant-a:same-item"
        assert await load(Tenant("tenant-b"), "same-item") == "tenant-b:same-item"


@pytest.mark.asyncio
async def test_default_key_keeps_static_method_object_argument() -> None:
    class Tenant:
        def __init__(self, name: str) -> None:
            self.name = name

    class StaticLoader:
        @staticmethod
        @cached(prefix="aud495-static")
        async def load(tenant: Tenant, item_id: str) -> str:
            return f"{tenant.name}:{item_id}"

    cache = MemoryCache()
    with patch("app.deps.cache.get_cache", return_value=cache):
        assert (
            await StaticLoader.load(Tenant("tenant-a"), "same-item")
            == "tenant-a:same-item"
        )
        assert (
            await StaticLoader.load(Tenant("tenant-b"), "same-item")
            == "tenant-b:same-item"
        )


@pytest.mark.asyncio
async def test_backend_error_logs_do_not_emit_cache_key_or_exception_text() -> None:
    secret_key = secrets.token_urlsafe(32)

    with patch("app.deps.cache.logger") as cache_logger:
        for cache in (
            RedisCache(url="redis://localhost:6379/0", default_ttl=60),
            RedisClusterCache(url="redis://localhost:6379/0", default_ttl=60),
        ):
            fake = AsyncMock()
            for operation in ("get", "set", "delete"):
                getattr(fake, operation).side_effect = RedisError(secret_key)
            cache._client = fake
            await cache.get(secret_key)
            await cache.set(secret_key, "payload")
            await cache.invalidate(secret_key)

        nats = NatsKVCache(bucket="cache", default_ttl=60)
        fake_kv = AsyncMock()
        for operation in ("get", "put", "delete"):
            getattr(fake_kv, operation).side_effect = OSError(secret_key)
        nats._kv = fake_kv
        await nats.get(secret_key)
        await nats.set(secret_key, "payload")
        await nats.invalidate(secret_key)

        class CredentialIdentifier:
            def __str__(self) -> str:
                return secret_key

        @cached(prefix="aud495-key-derived-from-object")
        async def lookup(credential: CredentialIdentifier) -> str:
            return "payload"

        keyed_cache = RedisCache(url="redis://localhost:6379/0", default_ttl=60)
        keyed_fake = AsyncMock()
        keyed_fake.get.side_effect = RedisError(secret_key)
        keyed_fake.set.side_effect = RedisError(secret_key)
        keyed_cache._client = keyed_fake
        with patch("app.deps.cache.get_cache", return_value=keyed_cache):
            await lookup(CredentialIdentifier())

        assert keyed_fake.get.await_args.args[0] == (
            f"aud495-key-derived-from-object:{secret_key}"
        )

    calls = [*cache_logger.debug.call_args_list, *cache_logger.warning.call_args_list]
    assert calls
    assert all(secret_key not in repr(call) for call in calls)
    assert all(not call.kwargs.get("exc_info") for call in calls)


@pytest.mark.asyncio
async def test_invalid_payload_logs_redact_cache_key() -> None:
    secret_key = secrets.token_urlsafe(32)

    with patch("app.deps.cache.logger") as cache_logger:
        for cache in (
            RedisCache(url="redis://localhost:6379/0", default_ttl=60),
            RedisClusterCache(url="redis://localhost:6379/0", default_ttl=60),
        ):
            fake = AsyncMock()
            fake.get.return_value = "not-json"
            fake.delete.return_value = 1
            cache._client = fake
            await cache.get(secret_key)

    calls = cache_logger.debug.call_args_list
    assert calls
    assert all(secret_key not in repr(call) for call in calls)


@pytest.mark.asyncio
async def test_backend_error_with_lone_surrogate_key_is_handled() -> None:
    cache_key = "tenant-\ud800"
    cache = RedisCache(url="redis://localhost:6379/0", default_ttl=60)
    fake = AsyncMock()
    fake.get.side_effect = RedisError(cache_key)
    cache._client = fake

    with patch("app.deps.cache.logger") as cache_logger:
        assert await cache.get(cache_key) is None

    calls = cache_logger.warning.call_args_list
    assert calls
    assert all(cache_key not in repr(call) for call in calls)
