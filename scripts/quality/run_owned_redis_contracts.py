"""Run Redis contracts only against the integration job's owned services.

The reviewed workflow supplies runner service IDs, never caller-selected URLs.
Markers are test-control capabilities, not Redis credentials. They live only in
the pytest child environment and expire even if the job is forcibly cancelled.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass

_IMAGE = (
    "redis:7-alpine@sha256:"
    "e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2"
)
_TTL = 7200
_CREATE = "return redis.call('SET',KEYS[1],ARGV[2],'NX','EX',ARGV[1])"
_DELETE = (
    "if redis.call('GET',KEYS[1]) == ARGV[1] then "
    "return redis.call('DEL',KEYS[1]) else return 0 end"
)


class OwnedRedisError(RuntimeError):
    """An opaque failure that must never grant a disposable-store capability."""


@dataclass(frozen=True)
class Store:
    container_id: str
    port: int
    run_id: str
    prefix: str
    key: str
    value: str


def _command(docker: str, *args: str, value: str | None = None) -> str:
    try:
        result = subprocess.run(
            [docker, *args],
            input=value,
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        raise OwnedRedisError("Docker transport failed") from None
    if result.returncode != 0:
        raise OwnedRedisError("Docker operation failed")
    return result.stdout.strip()


def _inspect(docker: str, container_id: str, port: int) -> None:
    try:
        records = json.loads(_command(docker, "inspect", container_id))
        if not isinstance(records, list) or len(records) != 1:
            raise OwnedRedisError("Service identity unavailable")
        record = records[0]
        bindings = record["HostConfig"]["PortBindings"]["6379/tcp"]
        valid = (
            record["Id"] == container_id
            and record["State"]["Running"] is True
            and record["Config"]["Image"] == _IMAGE
            and isinstance(bindings, list)
            and bool(bindings)
            and all(
                binding["HostPort"] == str(port)
                and binding["HostIp"] in ("", "0.0.0.0", "::", "127.0.0.1", "::1")
                for binding in bindings
            )
        )
    except (KeyError, TypeError, ValueError):
        raise OwnedRedisError("Service identity unavailable") from None
    if not valid:
        raise OwnedRedisError("Service identity mismatch")


def _redis(docker: str, container_id: str, *args: str, value: str | None = None) -> str:
    stdin_option = ("-x",) if value is not None else ()
    return _command(
        docker,
        "exec",
        "-i",
        container_id,
        "redis-cli",
        "--raw",
        "-n",
        "0",
        *stdin_option,
        *args,
        value=value,
    )


def _run_id(docker: str, container_id: str) -> str:
    info = _redis(docker, container_id, "INFO", "server")
    values = [
        line.removeprefix("run_id:")
        for line in info.splitlines()
        if line.startswith("run_id:")
    ]
    if len(values) != 1 or re.fullmatch(r"[0-9a-f]{40}", values[0]) is None:
        raise OwnedRedisError("Redis server identity unavailable")
    return values[0]


def _same_store(docker: str, store: Store) -> None:
    _inspect(docker, store.container_id, store.port)
    if not hmac.compare_digest(_run_id(docker, store.container_id), store.run_id):
        raise OwnedRedisError("Redis server identity changed")


def main(args: list[str] | None = None) -> int:
    created: list[Store] = []
    docker = shutil.which("docker") or ""
    status = 1
    cleanup_failed = False
    try:
        if (
            not docker
            or os.environ.get("RUN_INTEGRATION_TESTS") != "1"
            or os.environ.get("REDIS_URL") != "redis://localhost:6379"
            or os.environ.get("REVOCATION_REDIS_URL") != "redis://localhost:6380/0"
            or os.environ.get("CACHE_REDIS_URL", "redis://localhost:6379")
            not in ("redis://localhost:6379", "redis://localhost:6379/0")
        ):
            raise OwnedRedisError("Owned integration configuration required")
        specifications = (
            ("AUD428_CACHE_CONTAINER_ID", 6379, "AUD428_REDIS"),
            ("AUD428_REVOCATION_CONTAINER_ID", 6380, "AUD428_REVOCATION_REDIS"),
        )
        container_ids = [os.environ.get(name, "") for name, _, _ in specifications]
        if len(set(container_ids)) != 2 or any(
            re.fullmatch(r"[0-9a-f]{64}", value) is None for value in container_ids
        ):
            raise OwnedRedisError("Distinct runner service IDs required")
        stores: list[Store] = []
        for container_id, (_, port, prefix) in zip(
            container_ids, specifications, strict=True
        ):
            _inspect(docker, container_id, port)
            stores.append(
                Store(
                    container_id,
                    port,
                    _run_id(docker, container_id),
                    prefix,
                    "aud428-owner:" + uuid.uuid4().hex,
                    secrets.token_hex(32),
                )
            )
        if hmac.compare_digest(stores[0].run_id, stores[1].run_id):
            raise OwnedRedisError("Distinct Redis servers required")
        for store in stores:
            # Mask before transport or child-environment handoff; never print
            # values in ordinary diagnostics or pass them in process arguments.
            print(f"::add-mask::{store.key}", flush=True)
            print(f"::add-mask::{store.value}", flush=True)
            _same_store(docker, store)
            applied = _redis(
                docker,
                store.container_id,
                "EVAL",
                _CREATE,
                "1",
                store.key,
                str(_TTL),
                value=store.value,
            )
            if applied != "OK":
                raise OwnedRedisError("Ownership marker was not established")
            # An uncertain SET acknowledgement does not grant cleanup authority;
            # its atomic expiry and job-owned container teardown are backstops.
            created.append(store)
            observed = _redis(docker, store.container_id, "GET", store.key)
            ttl = _redis(docker, store.container_id, "TTL", store.key)
            if (
                re.fullmatch(r"[0-9a-f]{64}", observed) is None
                or not hmac.compare_digest(observed, store.value)
                or re.fullmatch(r"[0-9]{4}", ttl) is None
                or not 3600 <= int(ttl) <= _TTL
            ):
                raise OwnedRedisError("Ownership marker verification failed")
            _same_store(docker, store)
        child_env = os.environ.copy()
        for store in stores:
            child_env[f"{store.prefix}_OWNER_KEY"] = store.key
            child_env[f"{store.prefix}_OWNER_VALUE"] = store.value
        print("OWNED_REDIS_CONTRACTS_ESTABLISHED", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", *(sys.argv[1:] if args is None else args)],
            env=child_env,
            check=False,
        )
        status = (
            result.returncode if result.returncode >= 0 else 128 - result.returncode
        )
    except (OwnedRedisError, OSError, subprocess.SubprocessError):
        print("OWNED_REDIS_CONTRACTS_REJECTED", file=sys.stderr)
    finally:
        for store in reversed(created):
            try:
                _same_store(docker, store)
                removed = _redis(
                    docker,
                    store.container_id,
                    "EVAL",
                    _DELETE,
                    "1",
                    store.key,
                    value=store.value,
                )
                if removed != "1":
                    raise OwnedRedisError("Owned marker cleanup was not confirmed")
            except OwnedRedisError:
                cleanup_failed = True
        if cleanup_failed:
            print("OWNED_REDIS_CONTRACTS_CLEANUP_REJECTED", file=sys.stderr)
    return status or int(cleanup_failed)


if __name__ == "__main__":
    raise SystemExit(main())
