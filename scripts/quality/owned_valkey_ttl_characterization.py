"""Unpublished Valkey TTL characterization; not a production session writer.

The owning workflow must provide a dedicated, labelled loopback-only service.
No existing pytest cohorts or RedisSessionService behavior are replaced.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import re
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path

import redis
import yaml
from redis.exceptions import NoPermissionError, ResponseError

PORT = 6382
LABEL = "university-ecosystem.valkey-ttl-acceptance"
SCRIPT = """
local ttl = ARGV[1]
if not string.match(ttl, '^[1-9]%d*$') or #ttl > 10
   or tonumber(ttl) > 2147483647 then
    return redis.error_reply('TTL_REJECTED')
end
local kind = redis.call('TYPE', KEYS[1]).ok
if kind ~= 'none' and kind ~= 'hash' then
    return redis.error_reply('TYPE_REJECTED')
end
if not redis.acl_check_cmd('HSET', KEYS[1], 'value', ARGV[2])
   or not redis.acl_check_cmd('EXPIRE', KEYS[1], ttl) then
    return redis.error_reply('ACL_REJECTED')
end
redis.call('HSET', KEYS[1], 'value', ARGV[2])
return redis.call('EXPIRE', KEYS[1], ttl)
"""


class Rejected(RuntimeError):
    """Fixed diagnostic only: never expose provider or Docker output."""


class _PinLoader(yaml.SafeLoader):
    """Do not let YAML duplicate keys override reviewed image authority."""


def _pin_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        if key_node.value == "<<":
            raise Rejected("IMAGE_PIN_REJECTED")
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, (str, int, bool)) or key in result:
            raise Rejected("IMAGE_PIN_REJECTED")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


_PinLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _pin_mapping)


def _pin_document(path: Path):
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            raise Rejected("IMAGE_PIN_REJECTED")
        with path.open("rb") as stream:
            raw = stream.read(131073)
        if len(raw) > 131072:
            raise Rejected("IMAGE_PIN_REJECTED")
        text = raw.decode("utf-8")
        if any(isinstance(event, yaml.AliasEvent) for event in yaml.parse(text)):
            raise Rejected("IMAGE_PIN_REJECTED")
        loader = _PinLoader(text)
        try:
            value = loader.get_single_data()
        finally:
            loader.dispose()
        if not isinstance(value, dict):
            raise Rejected("IMAGE_PIN_REJECTED")
        return value
    except (OSError, UnicodeError, yaml.YAMLError):
        raise Rejected("IMAGE_PIN_REJECTED") from None


def _image_pin(root: Path) -> str:
    """Compose is the reviewed pin authority; the job must use that same pin."""
    try:
        compose = _pin_document(root / "docker-compose.yml")
        workflow = _pin_document(
            root / ".github/workflows/valkey-ttl-characterization.yml"
        )
        cache = compose["services"]["valkey"]["image"]
        revocation = compose["services"]["revocation-valkey"]["image"]
        job = workflow["jobs"]["characterize"]["services"]["valkey"]["image"]
        if (
            not isinstance(cache, str)
            or re.fullmatch(r"valkey/valkey:9\.1\.2-alpine@sha256:[0-9a-f]{64}", cache)
            is None
            or cache != revocation
            or cache != job
        ):
            raise Rejected("IMAGE_PIN_REJECTED")
        return cache
    except (KeyError, TypeError):
        raise Rejected("IMAGE_PIN_REJECTED") from None


def load_image_pin() -> str:
    return _image_pin(Path(__file__).resolve().parents[2])


@dataclass(frozen=True)
class Ownership:
    container_id: str
    run: str
    attempt: str
    job: str


async def _inspect_response(container_id: str) -> bytes:
    if re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
        raise Rejected("OWNERSHIP_REJECTED")
    writer = None
    try:
        async with asyncio.timeout(10):
            reader, writer = await asyncio.open_unix_connection(
                path="/var/run/docker.sock", limit=16384
            )
            request = (
                "GET /v1.47/containers/"
                + container_id
                + "/json HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n"
            )
            writer.write(request.encode("ascii"))
            await writer.drain()
            output = bytearray()
            while True:
                remaining = 147457 - len(output)
                chunk = await reader.read(min(65536, remaining))
                if not chunk:
                    return bytes(output)
                output.extend(chunk)
                if len(output) > 147456:
                    raise Rejected("OWNERSHIP_REJECTED")
    finally:
        if writer is not None:
            try:
                writer.close()
            finally:
                async with asyncio.timeout(1):
                    await writer.wait_closed()


def inspect_output(container_id: str) -> str:
    """One fixed read-only Engine request, not a general Docker API client.

    The local runner daemon is trusted. Possession of its Unix socket is NOT
    an OS-enforced read-only capability; this code only sends the fixed GET.
    """
    if re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
        raise Rejected("OWNERSHIP_REJECTED")
    try:
        if not stat.S_ISSOCK(os.lstat("/var/run/docker.sock").st_mode):
            raise Rejected("OWNERSHIP_REJECTED")
        output = asyncio.run(_inspect_response(container_id))
        headers, separator, body = output.partition(b"\r\n\r\n")
        if not separator or len(headers) > 16380 or len(body) > 131072:
            raise Rejected("OWNERSHIP_REJECTED")
        lines = headers.split(b"\r\n")
        if lines[0] not in (b"HTTP/1.0 200 OK", b"HTTP/1.1 200 OK"):
            raise Rejected("OWNERSHIP_REJECTED")
        lengths = []
        for line in lines[1:]:
            name, colon, value = line.partition(b":")
            if (
                not colon
                or not name
                or re.fullmatch(rb"[A-Za-z0-9-]+", name) is None
                or b"\x00" in value
            ):
                raise Rejected("OWNERSHIP_REJECTED")
            if name.lower() == b"transfer-encoding":
                raise Rejected("OWNERSHIP_REJECTED")
            if name.lower() == b"content-length":
                value = value.strip()
                if re.fullmatch(rb"[0-9]{1,6}", value) is None:
                    raise Rejected("OWNERSHIP_REJECTED")
                lengths.append(int(value))
        # HTTP/1.0 close-delimited responses are allowed; length, if supplied,
        # must be unique and exact. No chunked decoding or redirect fallback.
        if len(lengths) > 1 or (lengths and lengths[0] != len(body)):
            raise Rejected("OWNERSHIP_REJECTED")
        return body.decode("utf-8")
    except (OSError, ValueError, TimeoutError):
        raise Rejected("OWNERSHIP_REJECTED") from None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Rejected("OWNERSHIP_REJECTED")
        result[key] = value
    return result


def inspect_owned(owner: Ownership) -> None:
    if (
        re.fullmatch(r"[0-9a-f]{64}", owner.container_id) is None
        or re.fullmatch(r"[0-9]+", owner.run) is None
        or re.fullmatch(r"[1-9][0-9]*", owner.attempt) is None
        or re.fullmatch(r"[A-Za-z0-9_-]+", owner.job) is None
    ):
        raise Rejected("OWNERSHIP_REJECTED")
    output = inspect_output(owner.container_id)
    try:
        record = json.loads(output, object_pairs_hook=_unique_object)
        if not isinstance(record, dict):
            raise Rejected("OWNERSHIP_REJECTED")
        labels = record["Config"]["Labels"]
        expected_binding = [{"HostIp": "127.0.0.1", "HostPort": str(PORT)}]
        valid = (
            record["Id"] == owner.container_id
            and record["State"]["Running"] is True
            and record["Config"]["Image"] == load_image_pin()
            and labels[LABEL] == "true"
            and labels[LABEL + ".run"] == owner.run
            and labels[LABEL + ".attempt"] == owner.attempt
            and labels[LABEL + ".job"] == owner.job
            and record["HostConfig"]["PortBindings"] == {"6379/tcp": expected_binding}
            and record["NetworkSettings"]["Ports"] == {"6379/tcp": expected_binding}
            and record["Mounts"] == []
        )
    except (KeyError, TypeError, ValueError):
        raise Rejected("OWNERSHIP_REJECTED") from None
    if not valid:
        raise Rejected("OWNERSHIP_REJECTED")


def snapshot(admin: redis.Redis, key: str) -> tuple:
    # Absolute expiry avoids a comparison against a decreasing TTL/local clock.
    with admin.pipeline(transaction=True) as pipe:
        pipe.type(key)
        pipe.dump(key)
        pipe.execute_command("PEXPIRETIME", key)
        return tuple(pipe.execute())


def expect_denial(
    admin: redis.Redis,
    client: redis.Redis,
    key: str,
    ttl: str,
    expected: str,
) -> None:
    before = snapshot(admin, key)
    try:
        client.eval(SCRIPT, 1, key, ttl, "replacement")
    except ResponseError as error:
        if expected == "NOPERM":
            if not isinstance(error, NoPermissionError):
                raise Rejected("UNEXPECTED_DENIAL") from None
        elif type(error) is not ResponseError or str(error) != expected:
            raise Rejected("UNEXPECTED_DENIAL") from None
    else:
        raise Rejected("DENIAL_NOT_OBSERVED")
    if snapshot(admin, key) != before:
        raise Rejected("DENIAL_MUTATED_KEY")


def transaction_control(admin, client, key: str, permissions) -> None:
    # Queue acknowledgements precede ACL change: execute_command does not
    # buffer like a redis-py Pipeline. Use one dedicated connection.
    with client.client() as transaction:
        connection = transaction.connection
        if connection is None:
            raise Rejected("DEDICATED_CONNECTION_MISSING")

        try:

            def raw_command(*args):
                connection.send_command(*args)
                return connection.read_response()

            if raw_command("MULTI") != b"OK":
                raise Rejected("QUEUE_CONTROL_FAILED")
            if raw_command("HSET", key, "value", "partial") != b"QUEUED":
                raise Rejected("QUEUE_CONTROL_FAILED")
            if raw_command("EXPIRE", key, 1200) != b"QUEUED":
                raise Rejected("QUEUE_CONTROL_FAILED")
            before_expiry = admin.execute_command("PEXPIRETIME", key)
            permissions("-expire")
            result = raw_command("EXEC")
            if (
                not isinstance(result, list)
                or len(result) != 2
                or not isinstance(result[0], int)
                or not isinstance(result[1], NoPermissionError)
                or admin.hget(key, "value") != b"partial"
                or admin.execute_command("PEXPIRETIME", key) != before_expiry
            ):
                raise Rejected("PARTIAL_WRITE_CONTROL_FAILED")
        finally:
            # Raw MULTI failures must never return a transactional socket.
            connection.disconnect()


def characterize(admin: redis.Redis, check_owner) -> None:
    prefix = "ttl-acceptance:" + secrets.token_hex(16)
    username = "ttl_acceptance_" + secrets.token_hex(16)
    password = secrets.token_hex(32)
    keys = [prefix + ":" + suffix for suffix in ("new", "old", "wrongtype")]
    created_user = False
    owned_keys = False
    client = None

    def permissions(*denied: str) -> None:
        check_owner()
        admin.execute_command(
            "ACL",
            "SETUSER",
            username,
            "reset",
            "on",
            ">" + password,
            "~" + prefix + ":*",
            "+ping",
            "+type",
            "+hset",
            "+expire",
            "+eval",
            "+multi",
            "+exec",
            *denied,
        )

    try:
        check_owner()
        if admin.execute_command("ACL", "GETUSER", username) is not None:
            raise Rejected("USER_COLLISION")
        if admin.exists(*keys):
            raise Rejected("KEY_COLLISION")
        # Dedicated fixture plus fresh random namespace owns these exact keys.
        owned_keys = True
        # Register cleanup responsibility before sending a possibly committed write.
        created_user = True
        permissions()
        client = redis.Redis(
            host="127.0.0.1",
            port=PORT,
            username=username,
            password=password,
            socket_timeout=3,
            socket_connect_timeout=3,
            protocol=2,
        )
        check_owner()
        admin.hset(keys[1], mapping={"value": "original", "retained": "yes"})
        admin.expire(keys[1], 3600)
        admin.set(keys[2], "wrongtype", ex=3600)
        for denied in ("-hset", "-expire", "-eval"):
            permissions(denied)
            for key in keys[:2]:
                expect_denial(
                    admin,
                    client,
                    key,
                    "600",
                    "NOPERM" if denied == "-eval" else "ACL_REJECTED",
                )
        permissions()
        for ttl in ("0", "-1", "1.5", "invalid", "2147483648"):
            for key in keys[:2]:
                expect_denial(admin, client, key, ttl, "TTL_REJECTED")
        expect_denial(admin, client, keys[2], "600", "TYPE_REJECTED")
        expect_denial(admin, client, prefix + "-outside:key", "600", "NOPERM")
        check_owner()
        for key in keys[:2]:
            if client.eval(SCRIPT, 1, key, "600", "replacement") != 1:
                raise Rejected("POSITIVE_CONTROL_FAILED")
            if admin.hget(key, "value") != b"replacement":
                raise Rejected("POSITIVE_CONTROL_FAILED")
            if not 0 < admin.ttl(key) <= 600:
                raise Rejected("POSITIVE_CONTROL_FAILED")
        if admin.hget(keys[1], "retained") != b"yes":
            raise Rejected("HASH_CONTRACT_CHANGED")

        transaction_control(admin, client, keys[0], permissions)
    finally:
        close_failed = False
        if client is not None:
            try:
                client.close()
            except Exception:
                close_failed = True
        # Identity change forbids deletion, even at the cost of retaining fixture
        # data until the owning job destroys its disposable container.
        check_owner()
        if created_user:
            admin.execute_command("ACL", "DELUSER", username)
        if owned_keys:
            admin.delete(*keys)
        if close_failed:
            raise Rejected("CLIENT_CLEANUP_REJECTED")


def main() -> int:
    admin = None
    status = 0
    try:
        if importlib.metadata.version("redis") != "8.1.0":
            raise Rejected("CLIENT_VERSION_REJECTED")
        owner = Ownership(
            os.environ.get("TTL_ACCEPTANCE_CONTAINER_ID", ""),
            os.environ.get("GITHUB_RUN_ID", ""),
            os.environ.get("GITHUB_RUN_ATTEMPT", ""),
            os.environ.get("GITHUB_JOB", ""),
        )
        inspect_owned(owner)
        admin = redis.Redis(
            host="127.0.0.1",
            port=PORT,
            socket_timeout=3,
            socket_connect_timeout=3,
            protocol=2,
        )
        info = admin.info("server")
        run_id = info.get("run_id")
        if (
            info.get("valkey_version") != "9.1.2"
            or not isinstance(run_id, str)
            or re.fullmatch(r"[0-9a-f]{40}", run_id) is None
        ):
            raise Rejected("SERVER_VERSION_REJECTED")

        def check_owner() -> None:
            inspect_owned(owner)
            if admin.info("server").get("run_id") != run_id:
                raise Rejected("SERVER_REPLACED")

        characterize(admin, check_owner)
    except Exception:
        print("VALKEY_TTL_CHARACTERIZATION_REJECTED")
        status = 1
    finally:
        if admin is not None:
            try:
                admin.close()
            except Exception:
                print("VALKEY_TTL_CHARACTERIZATION_CLEANUP_REJECTED")
                status = 1
    if status == 0:
        print("VALKEY_TTL_CHARACTERIZATION_PASSED")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
