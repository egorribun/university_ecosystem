"""Regressions for test oracles that must reject a false-green outcome."""

from __future__ import annotations

import asyncio
import importlib.machinery
import importlib.util
import secrets
import uuid
from pathlib import Path
from types import CodeType, SimpleNamespace
from typing import Any

import pytest

from tests.integration import test_redis_contract as redis_contract
from tests.integration.test_redis_contract import (
    test_redis_keyspace_notifications_contract as _keyspace_contract,
)
from tests.integration.test_redis_contract import (
    test_revocation_key_format as _revocation_contract,
)


class _RedisProbe:
    def __init__(self, notification: str = "bytes") -> None:
        self.notification = notification
        self.owner_key = f"aud428-owner:{uuid.uuid4().hex}"
        self.owner_value = secrets.token_hex(32)
        self.owner_present = True
        self.connection_pool = SimpleNamespace(connection_kwargs={"db": 0})
        self.server_id = uuid.uuid4().hex + secrets.token_hex(4)
        self.flags = "Kg"
        self.config_changes: list[str] = []
        self.fail_next_config_set = False
        self.fail_config_get = False
        self.invalid_config: str | None = None
        self.fail_subscribe = False
        self.ignore_restore = False
        self.fail_marker_read = False
        self.lose_owner_on_close = False
        self.replace_server_on_close = False
        self.replace_server_on_config_read = False
        self.key: str | None = None
        self.closed = False
        self.deleted: list[str] = []
        self.channel = ""
        self.awaiting_ack = False
        self.operations: list[str] = []

    async def get(self, key: str) -> bytes | None:
        if self.fail_marker_read:
            raise OSError("marker read failed")
        if key != self.owner_key or not self.owner_present:
            return None
        return self.owner_value.encode()

    async def config_get(self, name: str) -> dict[str, Any]:
        if self.fail_config_get:
            raise OSError("config read failed")
        if self.replace_server_on_config_read:
            self.replace_server_on_config_read = False
            self.server_id = uuid.uuid4().hex + secrets.token_hex(4)
        if self.invalid_config == "missing":
            return {}
        if self.invalid_config == "malformed":
            return {name: 1}
        return {name: self.flags}

    async def info(self, _section: str) -> dict[str, str]:
        return {"run_id": self.server_id}

    async def config_set(self, _name: str, value: str) -> bool:
        self.config_changes.append(value)
        if not (self.ignore_restore and value == "Kg"):
            self.flags = value
        if self.fail_next_config_set:
            self.fail_next_config_set = False
            raise OSError("config write acknowledgement lost")
        return True

    def pubsub(self) -> _RedisProbe:
        return self

    async def subscribe(self, channel: str) -> None:
        if self.fail_subscribe:
            raise OSError("subscribe failed")
        self.operations.append("subscribe")
        self.channel = channel
        self.awaiting_ack = True

    async def set(self, key: str, _value: str, *, ex: int) -> bool:
        self.operations.append("set")
        self.key = key
        return True

    async def exists(self, _key: str) -> int:
        return 0

    async def get_message(self, **_kwargs: Any) -> dict[str, Any] | None:
        if self.awaiting_ack:
            self.awaiting_ack = False
            self.operations.append("ack")
            return {"type": "subscribe", "channel": self.channel.encode(), "data": 1}
        if self.notification == "none":
            return None
        if self.notification == "other":
            return {
                "type": "message",
                "channel": self.channel.encode(),
                "data": b"unrelated-expiration",
            }
        if self.notification == "other_channel":
            return {
                "type": "message",
                "channel": b"unrelated-channel",
                "data": self.key.encode() if self.key else b"",
            }
        assert self.key is not None
        data = self.key if self.notification == "string" else self.key.encode()
        return {"type": "message", "channel": self.channel.encode(), "data": data}

    async def unsubscribe(self, _channel: str) -> None:
        pass

    async def aclose(self) -> None:
        self.closed = True
        if self.lose_owner_on_close:
            self.owner_present = False
        if self.replace_server_on_close:
            self.server_id = uuid.uuid4().hex + secrets.token_hex(4)

    async def delete(self, key: str) -> None:
        self.deleted.append(key)


def _admit_redis(monkeypatch: pytest.MonkeyPatch, redis: _RedisProbe) -> None:
    monkeypatch.setenv("AUD428_REDIS_OWNER_KEY", redis.owner_key)
    monkeypatch.setenv("AUD428_REDIS_OWNER_VALUE", redis.owner_value)
    monkeypatch.setattr(redis_contract, "_EXPIRY_EVENT_TIMEOUT_SECONDS", 0.03)


class _OptimizedSourceLoader(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname: str) -> CodeType:
        source = self.get_data(self.path)
        return self.source_to_code(source, self.path, _optimize=1)


def _optimized_expiry_probe(
    source_path: Path, monkeypatch: pytest.MonkeyPatch
) -> _RedisProbe:
    loader = _OptimizedSourceLoader(
        "_aud428_optimized_redis_contract", str(source_path)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError("Could not construct the optimized source loader")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    redis = _RedisProbe()
    _admit_redis(monkeypatch, redis)
    monkeypatch.setattr(module, "_EXPIRY_EVENT_TIMEOUT_SECONDS", 0.03)
    asyncio.run(module.test_redis_keyspace_notifications_contract(redis))
    return redis


def test_expiry_writes_and_restoration_survive_optimized_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _optimized_expiry_probe(Path(redis_contract.__file__), monkeypatch)

    assert redis.key is not None
    assert redis.operations == ["subscribe", "ack", "set"]
    assert redis.config_changes == ["KgEx", "Kg"]
    assert redis.flags == "Kg"
    assert redis.closed
    assert redis.deleted == [redis.key]


@pytest.mark.parametrize("notification", ["none", "other", "other_channel"])
def test_keyspace_contract_rejects_missing_matching_expiration(
    notification: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    redis = _RedisProbe(notification)
    _admit_redis(monkeypatch, redis)

    with pytest.raises(AssertionError, match="Expected Redis pubsub message"):
        asyncio.run(_keyspace_contract(redis))

    assert redis.closed
    assert redis.deleted == [redis.key]
    assert redis.flags == "Kg"
    assert redis.config_changes[-1] == "Kg"
    assert redis.operations == ["subscribe", "ack", "set"]


@pytest.mark.parametrize("notification", ["bytes", "string"])
def test_keyspace_contract_accepts_its_matching_expiration(
    notification: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    redis = _RedisProbe(notification)
    _admit_redis(monkeypatch, redis)

    asyncio.run(_keyspace_contract(redis))

    assert redis.closed
    assert redis.deleted == [redis.key]
    assert redis.flags == "Kg"
    assert redis.config_changes == ["KgEx", "Kg"]
    assert redis.operations == ["subscribe", "ack", "set"]


@pytest.mark.parametrize(
    "failure",
    [
        "missing_key",
        "missing_value",
        "bad_key",
        "bad_value",
        "wrong_db",
        "marker_missing",
        "marker_mismatch",
        "marker_error",
        "config_error",
        "config_missing",
        "config_malformed",
    ],
)
def test_expiry_probe_refuses_unowned_or_unreadable_configuration(
    failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    redis = _RedisProbe()
    _admit_redis(monkeypatch, redis)
    if failure == "missing_key":
        monkeypatch.delenv("AUD428_REDIS_OWNER_KEY")
    elif failure == "missing_value":
        monkeypatch.delenv("AUD428_REDIS_OWNER_VALUE")
    elif failure == "bad_key":
        monkeypatch.setenv("AUD428_REDIS_OWNER_KEY", "not-an-owner-marker")
    elif failure == "bad_value":
        monkeypatch.setenv("AUD428_REDIS_OWNER_VALUE", "invalid")
    elif failure == "wrong_db":
        redis.connection_pool.connection_kwargs["db"] = 1
    elif failure == "marker_missing":
        redis.owner_present = False
    elif failure == "marker_mismatch":
        redis.owner_value = secrets.token_hex(32)
    elif failure == "marker_error":
        redis.fail_marker_read = True
    elif failure == "config_error":
        redis.fail_config_get = True
    elif failure == "config_missing":
        redis.invalid_config = "missing"
    elif failure == "config_malformed":
        redis.invalid_config = "malformed"

    with pytest.raises((AssertionError, OSError)):
        asyncio.run(_keyspace_contract(redis))

    assert redis.config_changes == []
    assert redis.key is None
    assert redis.deleted == []


def test_expiry_probe_restores_after_uncertain_config_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _RedisProbe()
    _admit_redis(monkeypatch, redis)
    redis.fail_next_config_set = True

    with pytest.raises(OSError, match="config write acknowledgement lost"):
        asyncio.run(_keyspace_contract(redis))

    assert redis.config_changes == ["KgEx", "Kg"]
    assert redis.flags == "Kg"
    assert redis.key is None


def test_expiry_probe_restores_after_subscribe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _RedisProbe()
    _admit_redis(monkeypatch, redis)
    redis.fail_subscribe = True

    with pytest.raises(OSError, match="subscribe failed"):
        asyncio.run(_keyspace_contract(redis))

    assert redis.closed
    assert redis.flags == "Kg"
    assert redis.config_changes == ["KgEx", "Kg"]
    assert len(redis.deleted) == 1
    assert redis.deleted[0].startswith("notify-test:")


def test_expiry_probe_rejects_unverified_config_restoration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _RedisProbe()
    _admit_redis(monkeypatch, redis)
    redis.ignore_restore = True

    with pytest.raises(AssertionError):
        asyncio.run(_keyspace_contract(redis))

    assert redis.closed
    assert redis.config_changes == ["KgEx", "Kg"]
    assert redis.flags == "KgEx"


def test_expiry_probe_does_not_write_after_ownership_is_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _RedisProbe()
    _admit_redis(monkeypatch, redis)
    redis.lose_owner_on_close = True

    with pytest.raises(AssertionError):
        asyncio.run(_keyspace_contract(redis))

    assert redis.closed
    assert redis.deleted == []
    assert redis.config_changes == ["KgEx"]


def test_expiry_probe_refuses_replacement_before_config_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _RedisProbe()
    _admit_redis(monkeypatch, redis)
    redis.replace_server_on_config_read = True

    with pytest.raises(AssertionError, match="server identity changed"):
        asyncio.run(_keyspace_contract(redis))

    assert redis.config_changes == []
    assert redis.deleted == []


def test_expiry_probe_refuses_replacement_even_with_copied_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _RedisProbe()
    _admit_redis(monkeypatch, redis)
    redis.replace_server_on_close = True

    with pytest.raises(AssertionError, match="server identity changed"):
        asyncio.run(_keyspace_contract(redis))

    assert redis.closed
    assert redis.deleted == []
    assert redis.config_changes == ["KgEx"]


class _RevocationProbe:
    def __init__(self, notification: str) -> None:
        self.notification = notification
        self.owner_key = f"aud428-owner:{uuid.uuid4().hex}"
        self.owner_value = secrets.token_hex(32)
        self.owner_present = True
        self.fail_marker_read = False
        self.connection_pool = SimpleNamespace(connection_kwargs={"db": 0})
        self.server_id: Any = uuid.uuid4().hex + secrets.token_hex(4)
        self.fail_info = False
        self.lose_owner_on_close = False
        self.replace_server_on_ack = False
        self.replace_server_on_close = False
        self.registration_count = 0
        self.revocation_count = 0
        self.jti = ""
        self.closed = False
        self.deleted: list[str] = []
        self.channel = ""
        self.awaiting_ack = False

    async def get(self, key: str) -> bytes | None:
        if self.fail_marker_read:
            raise OSError("marker read failed")
        if key != self.owner_key or not self.owner_present:
            return None
        return self.owner_value.encode()

    async def info(self, _section: str) -> dict[str, Any]:
        if self.fail_info:
            raise OSError("server identity unavailable")
        return {"run_id": self.server_id}

    async def register_session(self, *, jti: str, **_kwargs: Any) -> None:
        self.registration_count += 1
        self.jti = jti

    async def revoke_session(self, jti: str) -> None:
        self.revocation_count += 1
        if jti != self.jti:
            raise RuntimeError("The revoked session differs from the registered one")

    def pubsub(self) -> _RevocationProbe:
        return self

    async def subscribe(self, channel: str) -> None:
        self.channel = channel
        self.awaiting_ack = True

    async def exists(self, _key: str) -> int:
        return 1

    async def ttl(self, _key: str) -> int:
        return 60

    async def get_message(self, **_kwargs: Any) -> dict[str, str | bytes] | None:
        if self.awaiting_ack:
            self.awaiting_ack = False
            if self.replace_server_on_ack:
                self.server_id = uuid.uuid4().hex + secrets.token_hex(4)
            return {"type": "subscribe", "channel": self.channel.encode(), "data": "1"}
        if self.notification == "none":
            return None
        if self.notification == "wrong":
            return {"type": "message", "channel": self.channel, "data": "wrong-jti"}
        if self.notification == "unrelated":
            return {
                "type": "message",
                "channel": self.channel.encode(),
                "data": b"unrelated-event",
            }
        if self.notification == "other_channel":
            return {
                "type": "message",
                "channel": b"unrelated-channel",
                "data": self.jti.encode(),
            }
        data = self.jti.encode() if self.notification == "bytes" else self.jti
        return {"type": "message", "channel": self.channel.encode(), "data": data}

    async def unsubscribe(self, _channel: str) -> None:
        pass

    async def aclose(self) -> None:
        self.closed = True
        if self.lose_owner_on_close:
            self.owner_present = False
        if self.replace_server_on_close:
            self.server_id = uuid.uuid4().hex + secrets.token_hex(4)

    async def delete(self, key: str) -> None:
        self.deleted.append(key)


def _admit_redis_pair(
    monkeypatch: pytest.MonkeyPatch, cache: _RevocationProbe, redis: _RevocationProbe
) -> None:
    monkeypatch.setenv("AUD428_REDIS_OWNER_KEY", cache.owner_key)
    monkeypatch.setenv("AUD428_REDIS_OWNER_VALUE", cache.owner_value)
    monkeypatch.setenv("AUD428_REVOCATION_REDIS_OWNER_KEY", redis.owner_key)
    monkeypatch.setenv("AUD428_REVOCATION_REDIS_OWNER_VALUE", redis.owner_value)
    monkeypatch.setattr(redis_contract, "_EXPIRY_EVENT_TIMEOUT_SECONDS", 0.03)


@pytest.mark.parametrize(
    "notification", ["none", "wrong", "unrelated", "other_channel"]
)
def test_revocation_contract_rejects_missing_or_wrong_payload(
    notification: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    redis = _RevocationProbe(notification)
    cache = _RevocationProbe("none")
    _admit_redis_pair(monkeypatch, cache, redis)

    with pytest.raises(
        AssertionError, match=r"Expected Redis pubsub message \(message\)"
    ):
        asyncio.run(_revocation_contract(cache, redis, redis))

    assert redis.closed
    assert redis.registration_count == 1
    assert redis.revocation_count == 1
    assert cache.deleted == [f"session:{redis.jti}"]
    assert redis.deleted == [f"revoked:jti:{redis.jti}"]


@pytest.mark.parametrize("notification", ["bytes", "string"])
def test_revocation_contract_accepts_exact_payload_and_cleans_owned_keys(
    notification: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    redis = _RevocationProbe(notification)
    cache = _RevocationProbe("none")
    _admit_redis_pair(monkeypatch, cache, redis)

    asyncio.run(_revocation_contract(cache, redis, redis))

    assert redis.closed
    assert redis.registration_count == 1
    assert redis.revocation_count == 1
    assert cache.deleted == [f"session:{redis.jti}"]
    assert redis.deleted == [f"revoked:jti:{redis.jti}"]


@pytest.mark.parametrize(
    "failure",
    [
        "missing_cache_key",
        "missing_revocation_key",
        "bad_cache_value",
        "bad_revocation_value",
        "cache_db",
        "revocation_db",
        "cache_marker_missing",
        "revocation_marker_missing",
        "cache_marker_mismatch",
        "revocation_marker_mismatch",
        "marker_error",
        "info_error",
        "invalid_run_id",
        "same_server",
    ],
)
def test_revocation_probe_refuses_unowned_or_nonindependent_stores(
    failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    redis = _RevocationProbe("bytes")
    cache = _RevocationProbe("none")
    _admit_redis_pair(monkeypatch, cache, redis)
    if failure == "missing_cache_key":
        monkeypatch.delenv("AUD428_REDIS_OWNER_KEY")
    elif failure == "missing_revocation_key":
        monkeypatch.delenv("AUD428_REVOCATION_REDIS_OWNER_KEY")
    elif failure == "bad_cache_value":
        monkeypatch.setenv("AUD428_REDIS_OWNER_VALUE", "invalid")
    elif failure == "bad_revocation_value":
        monkeypatch.setenv("AUD428_REVOCATION_REDIS_OWNER_VALUE", "invalid")
    elif failure == "cache_db":
        cache.connection_pool.connection_kwargs["db"] = 1
    elif failure == "revocation_db":
        redis.connection_pool.connection_kwargs["db"] = 1
    elif failure == "cache_marker_missing":
        cache.owner_present = False
    elif failure == "revocation_marker_missing":
        redis.owner_present = False
    elif failure == "cache_marker_mismatch":
        cache.owner_value = secrets.token_hex(32)
    elif failure == "revocation_marker_mismatch":
        redis.owner_value = secrets.token_hex(32)
    elif failure == "marker_error":
        redis.fail_marker_read = True
    elif failure == "info_error":
        redis.fail_info = True
    elif failure == "invalid_run_id":
        redis.server_id = "invalid"
    elif failure == "same_server":
        redis.server_id = cache.server_id

    with pytest.raises((AssertionError, OSError)):
        asyncio.run(_revocation_contract(cache, redis, redis))

    assert redis.registration_count == 0
    assert redis.revocation_count == 0
    assert cache.deleted == []
    assert redis.deleted == []


def test_revocation_probe_does_not_touch_store_after_ownership_is_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _RevocationProbe("bytes")
    cache = _RevocationProbe("none")
    _admit_redis_pair(monkeypatch, cache, redis)
    redis.lose_owner_on_close = True

    with pytest.raises(AssertionError, match="not the owned disposable store"):
        asyncio.run(_revocation_contract(cache, redis, redis))

    assert redis.closed
    assert cache.deleted == [f"session:{redis.jti}"]
    assert redis.deleted == []


@pytest.mark.parametrize("replacement_point", ["ack", "close"])
def test_revocation_probe_refuses_replacement_even_with_copied_marker(
    replacement_point: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    redis = _RevocationProbe("bytes")
    cache = _RevocationProbe("none")
    _admit_redis_pair(monkeypatch, cache, redis)
    redis.replace_server_on_ack = replacement_point == "ack"
    redis.replace_server_on_close = replacement_point == "close"

    with pytest.raises(AssertionError, match="server identity changed"):
        asyncio.run(_revocation_contract(cache, redis, redis))

    assert redis.closed
    assert cache.deleted == [f"session:{redis.jti}"]
    assert redis.deleted == []
    assert redis.revocation_count == (0 if replacement_point == "ack" else 1)
