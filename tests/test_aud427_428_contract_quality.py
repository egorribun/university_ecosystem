"""Regressions for test oracles that must reject a false-green outcome."""

from __future__ import annotations

import ast
import asyncio
import importlib.machinery
import importlib.util
import io
import json
import re
import runpy
import secrets
import shutil
import subprocess
import sys
import tokenize
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


class _OwnedRedisLauncherTransport:
    """Docker/pytest transport double; launcher admission and cleanup stay real."""

    image = (
        "redis:7-alpine@sha256:"
        "e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2"
    )
    ids = ("a" * 64, "b" * 64)

    def __init__(self, fault: str = "", pytest_status: int = 0) -> None:
        self.fault = fault
        self.pytest_status = pytest_status
        self.started = False
        self.markers: dict[str, tuple[str, str, int]] = {}
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.private: list[str] = []
        self.argv_private = False
        self.handoff_valid = False
        self.pytest_args: list[str] = []
        self.transport_canary = "synthetic-" + uuid.uuid4().hex
        self.server_ids = {self.ids[0]: "c" * 40, self.ids[1]: "d" * 40}
        self.info_counts = dict.fromkeys(self.ids, 0)

    def run(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        if command[0] == sys.executable:
            self.started = True
            self.pytest_args = command
            env = kwargs["env"]
            admitted = []
            for container_id, prefix in zip(
                self.ids, ("AUD428_REDIS", "AUD428_REVOCATION_REDIS"), strict=True
            ):
                marker = self.markers.get(container_id)
                admitted.append(
                    marker is not None
                    and env.get(prefix + "_OWNER_KEY") == marker[0]
                    and env.get(prefix + "_OWNER_VALUE") == marker[1]
                    and marker[2] == 7200
                )
            self.handoff_valid = all(admitted) and env.get("AUD428_SENTINEL") == "kept"
            if self.fault == "cleanup_identity":
                self.server_ids[self.ids[1]] = "e" * 40
            elif self.fault == "cleanup_marker":
                key, _, ttl = self.markers[self.ids[1]]
                self.markers[self.ids[1]] = (key, secrets.token_hex(32), ttl)
            return subprocess.CompletedProcess(command, self.pytest_status)

        assert command[0] == "/usr/bin/docker"
        assert kwargs["check"] is False
        assert kwargs["capture_output"] is True
        assert kwargs["timeout"] == 15
        value = kwargs["input"]
        if value is not None:
            self.private.append(value)
            self.argv_private |= any(value in arg for arg in command)
        if command[1] == "inspect":
            container_id = command[2]
            second = container_id == self.ids[1]
            if self.fault == "docker_nonzero":
                return subprocess.CompletedProcess(
                    command,
                    1,
                    stdout=self.transport_canary,
                    stderr=self.transport_canary,
                )
            if self.fault == "inspect_error":
                raise OSError(self.transport_canary)
            record = {
                "Id": container_id,
                "State": {"Running": not (second and self.fault == "stopped")},
                "Config": {
                    "Image": (
                        "unexpected" if second and self.fault == "image" else self.image
                    )
                },
                "HostConfig": {
                    "PortBindings": {
                        "6379/tcp": [
                            {
                                "HostIp": "",
                                "HostPort": (
                                    "6399"
                                    if second and self.fault == "port"
                                    else "6380"
                                    if second
                                    else "6379"
                                ),
                            }
                        ]
                    }
                },
            }
            if self.fault == "inspect_json":
                output = "invalid-json"
            else:
                output = json.dumps([] if self.fault == "inspect_shape" else [record])
        else:
            assert command[1:3] == ["exec", "-i"]
            container_id = command[3]
            assert container_id in self.ids
            assert command[4:8] == ["redis-cli", "--raw", "-n", "0"]
            args = command[8:]
            if args[0] == "-x":
                args = args[1:]
            else:
                assert value is None
            second = container_id == self.ids[1]
            if args == ["INFO", "server"]:
                self.info_counts[container_id] += 1
                run_id = self.server_ids[container_id]
                if (
                    second
                    and self.fault == "identity_before_write"
                    and self.info_counts[container_id] > 1
                ):
                    run_id = "e" * 40
                if second and self.fault == "same_server":
                    run_id = self.server_ids[self.ids[0]]
                if second and self.fault == "invalid_run_id":
                    run_id = "invalid"
                output = "run_id:" + run_id
            elif args[0] == "EVAL" and "'SET'" in args[1]:
                assert args[2] == "1"
                assert "'NX','EX'" in args[1]
                assert args[4] == "7200"
                key = args[3]
                assert re.fullmatch(r"aud428-owner:[0-9a-f]{32}", key)
                assert isinstance(value, str)
                value_valid = re.fullmatch(r"[0-9a-f]{64}", value) is not None
                assert value_valid, "ownership value must be bounded generated hex"
                if second and self.fault == "set_rejected":
                    output = ""
                else:
                    self.markers[container_id] = (key, value, 7200)
                    self.created.append(container_id)
                    if second and self.fault == "set_uncertain":
                        raise subprocess.TimeoutExpired(
                            command, 15, output=self.transport_canary
                        )
                    output = "OK"
            elif args[0] == "GET":
                output = self.markers[container_id][1]
                if second and self.fault == "readback":
                    output = "non-ASCII-\u00e9"
            elif args[0] == "TTL":
                output = "7200"
                if second and self.fault == "ttl_missing":
                    output = "-1"
                elif second and self.fault == "ttl_short":
                    output = "3599"
                elif second and self.fault == "ttl_unbounded":
                    output = "7201"
            else:
                assert args[0] == "EVAL" and "'DEL'" in args[1]
                assert "redis.call('GET',KEYS[1]) == ARGV[1]" in args[1]
                marker = self.markers.get(container_id)
                if marker is not None and marker[:2] == (args[3], value):
                    self.deleted.append(container_id)
                    del self.markers[container_id]
                    output = "1"
                else:
                    output = "0"
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")


def _owned_redis_launcher(
    monkeypatch: pytest.MonkeyPatch, transport: _OwnedRedisLauncherTransport
) -> Any:
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts/quality/run_owned_redis_contracts.py"
    module = runpy.run_path(str(path))
    monkeypatch.setattr(module["shutil"], "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(module["subprocess"], "run", transport.run)
    for name, value in {
        "RUN_INTEGRATION_TESTS": "1",
        "REDIS_URL": "redis://localhost:6379",
        "REVOCATION_REDIS_URL": "redis://localhost:6380/0",
        "AUD428_CACHE_CONTAINER_ID": transport.ids[0],
        "AUD428_REVOCATION_CONTAINER_ID": transport.ids[1],
        "AUD428_SENTINEL": "kept",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("CACHE_REDIS_URL", raising=False)
    return module["main"]


def _assert_launcher_output_is_bounded(
    transport: _OwnedRedisLauncherTransport, captured: Any
) -> None:
    ordinary = (
        "\n".join(
            line
            for line in captured.out.splitlines()
            if not line.startswith("::add-mask::")
        )
        + captured.err
    )
    private_exposed = any(
        value in ordinary for value in [*transport.private, transport.transport_canary]
    )
    assert not private_exposed, "launcher diagnostics exposed private control data"
    assert not transport.argv_private, "marker value appeared in process arguments"


def test_redis_launcher_is_bound_to_the_existing_integration_services() -> None:
    import yaml

    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load(
        (root / ".github/workflows/reusable-backend-tests.yml").read_text()
    )
    job = workflow["jobs"]["integration-tests"]
    assert job["timeout-minutes"] == 60
    for name, port in (("redis", 6379), ("revocation-redis", 6380)):
        assert job["services"][name]["image"] == _OwnedRedisLauncherTransport.image
        assert job["services"][name]["ports"] == [f"{port}:6379"]
    step = next(
        item for item in job["steps"] if item.get("name") == "Run integration tests"
    )
    assert step["env"]["AUD428_CACHE_CONTAINER_ID"] == "${{ job.services.redis.id }}"
    assert step["env"]["AUD428_REVOCATION_CONTAINER_ID"] == (
        "${{ job.services['revocation-redis'].id }}"
    )
    assert step["shell"] == "pwsh"
    run = step["run"]
    launcher = "uv run python scripts/quality/run_owned_redis_contracts.py @pytestArgs"
    assert launcher in run
    assert "uv run pytest @pytestArgs" not in run
    assert '"-x"' in run
    assert "$pytestArgs += $integrationShardArgs" in run


@pytest.mark.parametrize("pytest_status", [0, 7])
def test_owned_redis_launcher_hands_off_then_cleans_exact_markers(
    pytest_status: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    transport = _OwnedRedisLauncherTransport(pytest_status=pytest_status)
    main = _owned_redis_launcher(monkeypatch, transport)
    args = ["tests/integration/", "-v", "--tb=short", "-x"]
    status = main(args)
    captured = capsys.readouterr()
    assert status == pytest_status
    assert transport.handoff_valid
    assert transport.pytest_args == [sys.executable, "-m", "pytest", *args]
    assert transport.created == list(transport.ids)
    assert transport.deleted == list(reversed(transport.ids))
    markers_empty = not transport.markers
    assert markers_empty, "confirmed test markers must be cleaned"
    established = "OWNED_REDIS_CONTRACTS_ESTABLISHED" in captured.out
    assert established, "launcher must report established ownership"
    _assert_launcher_output_is_bounded(transport, captured)


@pytest.mark.parametrize(
    "fault",
    [
        "docker_missing",
        "missing_id",
        "equal_ids",
        "integration_disabled",
        "cache_url_empty",
        "url_override",
        "redis_url_override",
        "revocation_url_override",
        "inspect_error",
        "docker_nonzero",
        "inspect_json",
        "inspect_shape",
        "stopped",
        "image",
        "port",
        "same_server",
        "invalid_run_id",
    ],
)
def test_owned_redis_launcher_rejects_admission_before_any_marker_write(
    fault: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    transport = _OwnedRedisLauncherTransport(fault)
    main = _owned_redis_launcher(monkeypatch, transport)
    if fault == "docker_missing":
        monkeypatch.setattr(shutil, "which", lambda _name: None)
    elif fault == "integration_disabled":
        monkeypatch.setenv("RUN_INTEGRATION_TESTS", "0")
    elif fault == "missing_id":
        monkeypatch.delenv("AUD428_CACHE_CONTAINER_ID")
    elif fault == "equal_ids":
        monkeypatch.setenv("AUD428_REVOCATION_CONTAINER_ID", transport.ids[0])
    elif fault == "cache_url_empty":
        monkeypatch.setenv("CACHE_REDIS_URL", "")
    elif fault == "url_override":
        monkeypatch.setenv("CACHE_REDIS_URL", "redis://unowned.invalid:6379/0")
    elif fault == "redis_url_override":
        monkeypatch.setenv("REDIS_URL", "redis://unowned.invalid:6379/0")
    elif fault == "revocation_url_override":
        monkeypatch.setenv("REVOCATION_REDIS_URL", "redis://unowned.invalid:6380/0")
    status = main(["tests/integration/"])
    captured = capsys.readouterr()
    assert status == 1
    assert not transport.started
    assert transport.created == []
    assert transport.deleted == []
    _assert_launcher_output_is_bounded(transport, captured)


@pytest.mark.parametrize(
    "fault",
    [
        "identity_before_write",
        "set_rejected",
        "set_uncertain",
        "readback",
        "ttl_missing",
        "ttl_short",
        "ttl_unbounded",
    ],
)
def test_owned_redis_launcher_does_not_grant_partial_or_unverified_ownership(
    fault: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    transport = _OwnedRedisLauncherTransport(fault)
    main = _owned_redis_launcher(monkeypatch, transport)
    status = main(["tests/integration/"])
    captured = capsys.readouterr()
    assert status == 1
    assert not transport.started
    assert transport.ids[0] in transport.deleted
    if fault == "set_uncertain":
        # Only the atomically expiring unacknowledged marker remains.
        assert list(transport.markers) == [transport.ids[1]]
        expiry_is_bounded = transport.markers[transport.ids[1]][2] == 7200
        assert expiry_is_bounded, "unconfirmed write must retain its atomic expiry"
        assert transport.ids[1] not in transport.deleted
    else:
        markers_empty = not transport.markers
        assert markers_empty, "confirmed test markers must be cleaned"
    _assert_launcher_output_is_bounded(transport, captured)


@pytest.mark.parametrize("fault", ["cleanup_identity", "cleanup_marker"])
@pytest.mark.parametrize("pytest_status", [0, 7])
def test_owned_redis_launcher_cleanup_cannot_touch_a_replaced_owner(
    fault: str,
    pytest_status: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    transport = _OwnedRedisLauncherTransport(fault, pytest_status)
    main = _owned_redis_launcher(monkeypatch, transport)
    status = main(["tests/integration/"])
    captured = capsys.readouterr()
    assert status == (pytest_status or 1)
    assert transport.handoff_valid
    assert transport.deleted == [transport.ids[0]]
    assert list(transport.markers) == [transport.ids[1]]
    _assert_launcher_output_is_bounded(transport, captured)


def test_owned_redis_launcher_entrypoint_preserves_argument_boundaries(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    transport = _OwnedRedisLauncherTransport(pytest_status=7)
    _owned_redis_launcher(monkeypatch, transport)
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts/quality/run_owned_redis_contracts.py"
    args = ["tests/integration/", "-k", "revocation or keyspace", "-x"]
    monkeypatch.setattr(sys, "argv", [str(path), *args])
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(path), run_name="__main__")
    captured = capsys.readouterr()
    assert error.value.code == 7
    assert transport.pytest_args == [sys.executable, "-m", "pytest", *args]
    markers_empty = not transport.markers
    assert markers_empty, "confirmed test markers must be cleaned"
    _assert_launcher_output_is_bounded(transport, captured)


def _assert_owned_redis_ruff_scopes(source: str) -> None:
    """Accept only the three approved sites, never a general Ruff exemption."""
    tree = ast.parse(source)
    comments = [
        (token.start[0], token.string)
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
        and re.search(r"\bnoqa\b", token.string, re.IGNORECASE)
    ]
    expected_comments: list[tuple[int, str]] = []
    calls = {
        "_command": (
            "subprocess.run([docker, *args], input=value, text=True, "
            "capture_output=True, check=False, timeout=15)"
        ),
        "main": (
            "subprocess.run([sys.executable, '-m', 'pytest', "
            "*(sys.argv[1:] if args is None else args)], "
            "env=child_env, check=False)"
        ),
    }
    reasons = {
        "_command": "# noqa: S603 -- resolved Docker, fixed arguments",
        "main": "# noqa: S603 -- current interpreter, pytest arguments",
    }

    def function(name: str) -> ast.FunctionDef:
        matches = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        ]
        assert len(matches) == 1, "approved function identity must be unique"
        return matches[0]

    def is_subprocess_run(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
            and node.func.attr == "run"
        )

    def lexical_nodes(root: ast.AST) -> list[ast.AST]:
        pending: list[ast.AST] = (
            list(root.body) if isinstance(root, ast.FunctionDef) else [root]
        )
        nodes = []
        while pending:
            node = pending.pop()
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
            ):
                continue
            nodes.append(node)
            pending.extend(ast.iter_child_nodes(node))
        return nodes

    assert sum(is_subprocess_run(node) for node in ast.walk(tree)) == 2
    for name, expression in calls.items():
        matches = [
            node for node in lexical_nodes(function(name)) if is_subprocess_run(node)
        ]
        assert len(matches) == 1, "annotation must bind one approved subprocess call"
        expected = ast.parse(expression, mode="eval").body
        assert ast.dump(matches[0]) == ast.dump(expected)
        expected_comments.append((matches[0].lineno, reasons[name]))

    assignments = [
        node
        for node in lexical_nodes(function("_inspect"))
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "valid"
    ]
    assert len(assignments) == 1, "HostIp grant belongs to the admission predicate"
    expected_comparison = ast.parse(
        "binding['HostIp'] in ('', '0.0.0.0', '::', '127.0.0.1', '::1')",
        mode="eval",
    ).body
    comparisons = [
        node
        for node in lexical_nodes(assignments[0].value)
        if isinstance(node, ast.Compare)
        and ast.dump(node) == ast.dump(expected_comparison)
    ]
    assert len(comparisons) == 1, "HostIp grant must remain a metadata comparison"
    addresses = comparisons[0].comparators[0]
    assert isinstance(addresses, ast.Tuple)
    address = addresses.elts[1]
    expected_comments.append(
        (
            address.lineno,
            "# noqa: S104 -- inspected runner metadata, not a bind",
        )
    )
    assert sorted(comments) == sorted(expected_comments)


def test_owned_redis_launcher_ruff_annotations_are_source_bound() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts/quality/run_owned_redis_contracts.py").read_text()
    _assert_owned_redis_ruff_scopes(source)


@pytest.mark.parametrize(
    "mutation",
    [
        "extra",
        "missing",
        "moved",
        "nested_relocation",
        "broad",
        "file_level",
        "extra_rule",
        "docker_executable",
        "pytest_executable",
        "shell",
        "comparison_context",
    ],
)
def test_owned_redis_launcher_ruff_scope_rejects_unapproved_changes(
    mutation: str,
) -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts/quality/run_owned_redis_contracts.py").read_text()
    docker_comment = "# noqa: S603 -- resolved Docker, fixed arguments"
    host_comment = "# noqa: S104 -- inspected runner metadata, not a bind"
    replacements = {
        "extra": ("import hmac\n", "import hmac  # noqa: S603\n"),
        "missing": ("  " + docker_comment, ""),
        "moved": (
            "    try:\n        result = subprocess.run(  " + docker_comment,
            "    try:  " + docker_comment + "\n        result = subprocess.run(",
        ),
        "nested_relocation": (
            "    try:\n        result = subprocess.run(",
            "    try:\n        def relocated():\n            result = subprocess.run(",
        ),
        "broad": (host_comment, "# noqa"),
        "file_level": (
            "from __future__ import annotations\n",
            "# ruff: noqa\nfrom __future__ import annotations\n",
        ),
        "extra_rule": (
            docker_comment,
            "# noqa: S603, S104 -- resolved Docker, fixed arguments",
        ),
        "docker_executable": ("[docker, *args]", "[unapproved_docker, *args]"),
        "pytest_executable": (
            '[sys.executable, "-m", "pytest"',
            '[unapproved_python, "-m", "pytest"',
        ),
        "shell": (
            "            env=child_env,\n            check=False,",
            "            env=child_env,\n            check=False,\n"
            "            shell=True,",
        ),
        "comparison_context": (
            'binding["HostIp"] in (',
            "bind_host_ip(",
        ),
    }
    before, after = replacements[mutation]
    assert source.count(before) == 1
    mutated = source.replace(before, after)
    with pytest.raises(AssertionError):
        _assert_owned_redis_ruff_scopes(mutated)
