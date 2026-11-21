"""Owned RedisSessionService characterization, NOT a production TTL fix.

Run only in the dedicated Valkey acceptance job. The cancellation case stops at
an acknowledged HSET/application boundary; it does not simulate wire ambiguity.
Only fixed receipts leave this process. No real authentication token is used.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.metadata
import logging
import os
import re
import secrets
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import redis
import redis.asyncio as async_redis
from redis.exceptions import NoPermissionError

from scripts.quality import owned_valkey_ttl_characterization as fixture

URL = f"redis://127.0.0.1:{fixture.PORT}/0"


def require(condition: bool) -> None:
    if not condition:
        raise fixture.Rejected("SESSION_CONTRACT_REJECTED")


class SafeWarnings:
    """Count calls without formatting, retaining or emitting provider payloads."""

    def __init__(self):
        self.count = 0
        self.permission_denials = 0

    def warning(self, *args, **_kwargs):
        self.count += 1
        if args and isinstance(args[-1], NoPermissionError):
            self.permission_denials += 1


@contextmanager
def service_client(module, client):
    """Process-local injection, restored even on cancellation; no pool mutation."""
    original_client = module._get_shared_client
    original_logger = module.logger
    warnings = SafeWarnings()

    async def selected(url):
        require(url == URL)
        return client

    module._get_shared_client = selected
    module.logger = warnings
    try:
        yield warnings
    finally:
        module._get_shared_client = original_client
        module.logger = original_logger


class AfterHset:
    """Forward a real HSET, then stop before any EXPIRE dispatch."""

    def __init__(self, client):
        self.client = client
        self.acknowledged = asyncio.Event()
        self.block = asyncio.Event()
        self.expire_calls = 0

    async def hset(self, *args, **kwargs):
        result = await self.client.hset(*args, **kwargs)
        self.acknowledged.set()
        await self.block.wait()
        return result

    async def expire(self, *args, **kwargs):
        self.expire_calls += 1
        return await self.client.expire(*args, **kwargs)


async def cancel_after_hset(operation, barrier):
    task = asyncio.create_task(operation)
    acknowledged = asyncio.create_task(barrier.acknowledged.wait())
    try:
        async with asyncio.timeout(5):
            done, _pending = await asyncio.wait(
                {task, acknowledged}, return_when=asyncio.FIRST_COMPLETED
            )
        if task in done:
            await task
            raise fixture.Rejected("HSET_BARRIER_NOT_REACHED")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            require(task.cancelled())
        else:
            raise fixture.Rejected("CANCELLATION_NOT_PROPAGATED")
        require(barrier.expire_calls == 0)
    finally:
        for pending in (task, acknowledged):
            if not pending.done():
                pending.cancel()
        # Retrieve every outcome, including failure before acknowledgement, so
        # no background exception can reach the loop's raw exception reporter.
        await asyncio.gather(task, acknowledged, return_exceptions=True)


def server_milliseconds(admin):
    seconds, microseconds = admin.time()
    return seconds * 1000 + microseconds // 1000


async def refreshed(admin, key, ttl, operation):
    before = server_milliseconds(admin)
    await operation
    after = server_milliseconds(admin)
    expiry = admin.execute_command("PEXPIRETIME", key)
    require(before + ttl * 1000 <= expiry <= after + ttl * 1000)


async def exercise(admin, client, permissions, check_owner, module, jtis):
    """Actual service calls, byte-level state and absolute server TTL controls."""
    service = module.RedisSessionService(redis_url=URL)
    require(0 < service.ttl_seconds <= 3600)
    user = uuid4()
    session = uuid4()
    mfa = datetime(2026, 1, 1, tzinfo=UTC)
    fingerprint = module.SessionFingerprint(
        user_agent="acceptance",
        accept_language="en",
        ip_address="127.0.0.1",
        fingerprint_hash="acceptance-fingerprint",
    )
    keys = [service.KEY_PREFIX + jti for jti in jtis]

    async def create(index):
        await service.create_session(
            jtis[index],
            user,
            fingerprint,
            mfa,
            session_id=session,
            mfa_epoch=7,
        )

    def expected(raw):
        stamp = raw.get(b"created_at", b"")
        parsed = datetime.fromisoformat(stamp.decode("ascii"))
        require(parsed.tzinfo is not None)
        return {
            b"user_id": str(user).encode(),
            b"session_id": str(session).encode(),
            b"fingerprint_hash": b"acceptance-fingerprint",
            b"mfa_verified_at": mfa.isoformat().encode(),
            b"last_seen_at": stamp,
            b"created_at": stamp,
            b"is_active": b"1",
            b"mfa_epoch": b"7",
        }

    with service_client(module, client) as warnings:
        await asyncio.to_thread(check_owner)
        require(await service.get_session(jtis[0]) is None)
        await refreshed(admin, keys[0], service.ttl_seconds, create(0))
        original = admin.hgetall(keys[0])
        require(original == expected(original))
        require(
            await service.get_session(jtis[0])
            == {
                "user_id": str(user),
                "session_id": str(session),
                "fingerprint_hash": "acceptance-fingerprint",
                "mfa_verified_at": mfa.isoformat(),
                "last_seen_at": original[b"last_seen_at"].decode(),
                "created_at": original[b"created_at"].decode(),
                "is_active": True,
                "mfa_epoch": 7,
            }
        )
        admin.hset(keys[0], "last_seen_at", "2000-01-01T00:00:00+00:00")
        admin.expire(keys[0], 30)
        await refreshed(
            admin, keys[0], service.ttl_seconds, service.update_last_seen(jtis[0])
        )
        updated = admin.hgetall(keys[0])
        stamp = updated.pop(b"last_seen_at")
        require(datetime.fromisoformat(stamp.decode()).tzinfo is not None)
        require(stamp != b"2000-01-01T00:00:00+00:00")
        require(updated == {k: v for k, v in original.items() if k != b"last_seen_at"})

        # Preserve the current missing-key update contract: one field, cache miss.
        await refreshed(
            admin, keys[1], service.ttl_seconds, service.update_last_seen(jtis[1])
        )
        missing = admin.hgetall(keys[1])
        require(set(missing) == {b"last_seen_at"})
        require(
            datetime.fromisoformat(missing[b"last_seen_at"].decode()).tzinfo is not None
        )
        require(await service.get_session(jtis[1]) is None)

        # Optional fields and inactive state remain actual service semantics.
        await service.create_session(jtis[2], user, None, None)
        optional = await service.get_session(jtis[2])
        require(optional is not None)
        require(
            optional["session_id"] is None
            and optional["fingerprint_hash"] is None
            and optional["mfa_verified_at"] is None
            and optional["mfa_epoch"] == 0
        )
        admin.hset(keys[2], "is_active", "0")
        require(await service.get_session(jtis[2]) is None)
        require(warnings.count == 0)

        for denied in ("-hset", "-expire"):
            await permissions(denied)
            for index in (3, 4):
                await asyncio.to_thread(check_owner)
                admin.delete(keys[index])
                if index == 4:
                    admin.hset(keys[index], mapping={"retained": "old"})
                    admin.expire(keys[index], 1200)
                before = fixture.snapshot(admin, keys[index])
                count = warnings.count
                denials = warnings.permission_denials
                await create(index)
                require(warnings.count == count + 1)
                require(warnings.permission_denials == denials + 1)
                after = fixture.snapshot(admin, keys[index])
                if denied == "-hset":
                    require(after == before)
                else:
                    # This explicitly records the existing non-atomic behavior.
                    raw = admin.hgetall(keys[index])
                    retained = raw.pop(b"retained", None)
                    require(raw == expected(raw))
                    require(retained == (b"old" if index == 4 else None))
                    require(after[0] == b"hash")
                    require(after[2] == (before[2] if index == 4 else -1))
            await permissions()
            await refreshed(admin, keys[3], service.ttl_seconds, create(3))
            require(await service.get_session(jtis[3]) is not None)

        # A new missing key and an existing expiring hash survive cancellation
        # with the acknowledged write and old/no expiry, not a rollback claim.
        for index in (5, 6):
            await asyncio.to_thread(check_owner)
            if index == 6:
                admin.hset(keys[index], mapping={"retained": "old"})
                admin.expire(keys[index], 1200)
            old_expiry = admin.execute_command("PEXPIRETIME", keys[index])
            barrier = AfterHset(client)
            with service_client(module, barrier):
                await cancel_after_hset(create(index), barrier)
            raw = admin.hgetall(keys[index])
            retained = raw.pop(b"retained", None)
            require(raw == expected(raw))
            require(retained == (b"old" if index == 6 else None))
            require(
                admin.execute_command("PEXPIRETIME", keys[index])
                == (old_expiry if index == 6 else -1)
            )
            await refreshed(admin, keys[index], service.ttl_seconds, create(index))
            require(await service.get_session(jtis[index]) is not None)

        # Exact ACL keys, not a broad session namespace grant.
        try:
            await client.hset(keys[0] + ":outside", mapping={"value": "outside"})
        except NoPermissionError:
            require(admin.exists(keys[0] + ":outside") == 0)
        else:
            raise fixture.Rejected("NAMESPACE_CONTROL_FAILED")


async def characterize_service(admin, check_owner, module):
    prefix = "ttl-service-" + secrets.token_hex(16)
    jtis = [prefix + ":" + str(index) for index in range(7)]
    keys = [module.RedisSessionService.KEY_PREFIX + jti for jti in jtis]
    username = "ttl_service_" + secrets.token_hex(16)
    password = secrets.token_hex(32)
    client = None
    created_user = False
    owned_keys = False

    async def permissions(*denied):
        await asyncio.to_thread(check_owner)
        admin.execute_command(
            "ACL",
            "SETUSER",
            username,
            "reset",
            "on",
            ">" + password,
            *("~" + key for key in keys),
            "+ping",
            "+hset",
            "+hgetall",
            "+expire",
            *denied,
        )

    try:
        await asyncio.to_thread(check_owner)
        require(module.RedisSessionService.KEY_PREFIX == "session:v2:")
        require(admin.execute_command("ACL", "GETUSER", username) is None)
        require(not admin.exists(*keys))
        owned_keys = True
        created_user = True
        await permissions()
        client = async_redis.Redis(
            host="127.0.0.1",
            port=fixture.PORT,
            username=username,
            password=password,
            socket_timeout=3,
            socket_connect_timeout=3,
            protocol=2,
        )
        async with asyncio.timeout(90):
            await exercise(admin, client, permissions, check_owner, module, jtis)
    finally:
        close_failed = False
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                close_failed = True
        await asyncio.to_thread(check_owner)
        if created_user:
            admin.execute_command("ACL", "DELUSER", username)
        if owned_keys:
            admin.delete(*keys)
        if close_failed:
            raise fixture.Rejected("SESSION_CLIENT_CLEANUP_REJECTED")


def load_service():
    # Explicit isolated process configuration; never borrow application secrets.
    require(os.environ.get("ENVIRONMENT") == "test")
    require(os.environ.get("DATABASE_URL") == "sqlite+aiosqlite:///:memory:")
    require(os.environ.get("ENV_FILE_PATH") == "")
    require(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES") == "10")
    require(not any(key.endswith("_FILE") for key in os.environ))
    require("SECRET_KEY" not in os.environ)
    previous_disable = logging.root.manager.disable
    os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
    try:
        # Import-time configuration errors are reported only by the fixed main
        # receipt. Do not expose settings inputs or Redis exception payloads.
        logging.disable(logging.CRITICAL)
        module = importlib.import_module("app.services.auth.redis_session")
        require(not module.settings.has_development_fallbacks)
        return module
    finally:
        os.environ.pop("SECRET_KEY", None)
        logging.disable(previous_disable)


def main():
    admin = None
    status = 0
    try:
        require(importlib.metadata.version("redis") == "8.1.0")
        owner = fixture.Ownership(
            os.environ.get("TTL_ACCEPTANCE_CONTAINER_ID", ""),
            os.environ.get("GITHUB_RUN_ID", ""),
            os.environ.get("GITHUB_RUN_ATTEMPT", ""),
            os.environ.get("GITHUB_JOB", ""),
        )
        fixture.inspect_owned(owner)
        admin = redis.Redis(
            host="127.0.0.1",
            port=fixture.PORT,
            socket_timeout=3,
            socket_connect_timeout=3,
            protocol=2,
        )
        info = admin.info("server")
        run_id = info.get("run_id")
        require(
            info.get("valkey_version") == "9.1.2"
            and isinstance(run_id, str)
            and re.fullmatch(r"[0-9a-f]{40}", run_id) is not None
        )

        def check_owner():
            fixture.inspect_owned(owner)
            require(admin.info("server").get("run_id") == run_id)

        module = load_service()
        asyncio.run(characterize_service(admin, check_owner, module))
    except Exception:
        print("VALKEY_SESSION_CHARACTERIZATION_REJECTED")
        status = 1
    finally:
        if admin is not None:
            try:
                admin.close()
            except Exception:
                print("VALKEY_SESSION_CHARACTERIZATION_CLEANUP_REJECTED")
                status = 1
    if status == 0:
        print("VALKEY_SESSION_CHARACTERIZATION_PASSED")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
