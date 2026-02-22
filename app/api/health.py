from __future__ import annotations

import asyncio
import time
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.database import engine, get_pool_health_metrics, wait_db
from app.core.metrics import record_health_probe
from app.deps.cache import get_cache
from app.services.file_scanner import (
    check_file_scanner_health,
    scan_for_malware,  # noqa: F401 - imported for test mocking
)
from app.services.storage import S3Storage, StaticFSStorage
from app.utils.files import _get_storage_backend
from app.utils.migrations import migrations_are_current

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

router = APIRouter(tags=["health"])

_storage_probe_cache: dict[str, Any] = {
    "expires_at": 0.0,
    "status": "unknown",
    "latency": 0.0,
}


_health_cache: dict[str, Any] = {
    "expires_at": 0.0,
    "payload": {},
    "status_code": 200,
}


def reset_storage_probe_cache() -> None:
    _storage_probe_cache.update(
        {"expires_at": 0.0, "status": "unknown", "latency": 0.0}
    )


def reset_health_cache() -> None:
    _health_cache.update({"expires_at": 0.0, "payload": {}, "status_code": 200})


async def _lightweight_storage_probe(backend: Any) -> str | None:
    if isinstance(backend, StaticFSStorage):
        exists = await asyncio.to_thread(backend.base_dir.exists)
        return "ok" if exists else "error"
    if isinstance(backend, S3Storage):
        await asyncio.to_thread(
            backend.client.list_objects_v2, Bucket=backend.bucket, MaxKeys=0
        )
        return "ok"
    return None


async def _write_delete_storage_probe(backend: Any) -> str:
    probe_name = f"healthz/{uuid.uuid4().hex}.txt"
    try:
        probe_url = await backend.save_file(probe_name, b"", content_type="text/plain")
    except Exception:
        return "error"
    try:
        await backend.delete_file(probe_url)
    except Exception:
        return "error"
    return "ok"


async def _check_queue(conn: AsyncConnection) -> None:
    if not getattr(settings, "notifications_queue_in_memory_only", False):
        await conn.execute(text("SELECT 1 FROM notification_queue_jobs"))


async def _probe_storage() -> tuple[str, float]:
    now = time.monotonic()
    cached_expires_at = float(_storage_probe_cache.get("expires_at", 0.0) or 0.0)
    if cached_expires_at > now:
        status = str(_storage_probe_cache.get("status", "unknown"))
        latency_seconds = float(_storage_probe_cache.get("latency", 0.0) or 0.0)
        return status, latency_seconds

    start = time.perf_counter()
    _status: str | None = None
    try:
        backend = _get_storage_backend()
        if settings.health_storage_probe_enabled:
            _status = await _write_delete_storage_probe(backend)
        if _status is None:
            lightweight_status = await _lightweight_storage_probe(backend)
            if lightweight_status is not None:
                _status = lightweight_status
            else:
                _status = "disabled"
        elif _status == "error":
            lightweight_status = await _lightweight_storage_probe(backend)
            if lightweight_status is not None:
                _status = lightweight_status
    except Exception:
        _status = "error"
    elapsed = time.perf_counter() - start
    latency_seconds = max(elapsed, 0.0)
    _storage_probe_cache.update(
        {
            "expires_at": now
            + max(settings.health_storage_probe_min_interval_seconds, 0.0),
            "status": _status,
            "latency": latency_seconds,
        }
    )
    return _status or "unknown", latency_seconds


@router.get("/healthz")
async def healthz() -> JSONResponse:
    now = time.monotonic()
    if _health_cache["expires_at"] > now:
        return JSONResponse(
            status_code=_health_cache["status_code"],
            content=_health_cache["payload"],
        )

    statuses: dict[str, Any] = {}
    latencies: dict[str, float] = {}

    db_status = "ok"
    db_start = time.perf_counter()
    try:
        async with engine.connect() as conn:
            # 1. Connectivity check
            await conn.execute(text("SELECT 1"))

            # 2. Migrations check
            try:
                (
                    migrations_current,
                    current_versions,
                    expected_versions,
                ) = await migrations_are_current(conn=conn)
                if not migrations_current:
                    # Drift is always an error for the migration status itself
                    statuses["db_migrations"] = "error"
                    statuses["db_migrations_current"] = sorted(current_versions)
                    statuses["db_migrations_expected"] = sorted(expected_versions)

                    # But only trigger a global 503 if NOT in testing environment
                    # (In tests, we often auto-create schema without migrations)
                    is_test = settings.environment in ("testing", "test")
                    if not is_test:
                        db_status = "error"
                else:
                    statuses["db_migrations"] = "ok"
            except Exception:
                # If migrations check fails (e.g. table missing in SQLite),
                # only error out if not in testing.
                is_test = settings.environment in ("testing", "test")
                if not is_test:
                    db_status = "error"
                statuses["db_migrations"] = "skipped" if is_test else "error"

            # 3. Queue status
            queue_status = "ok"
            queue_start = time.perf_counter()
            try:
                await _check_queue(conn)
            except (OperationalError, Exception):
                queue_status = "error"
            queue_elapsed = time.perf_counter() - queue_start
            statuses["notification_queue"] = queue_status
            latencies["notification_queue_latency_ms"] = max(queue_elapsed * 1000, 0.0)
            record_health_probe("notification_queue", queue_status, queue_elapsed)

    except Exception:
        db_status = "error"

    statuses["db"] = db_status
    if db_status == "error":
        statuses.setdefault("db_migrations", "error")
    db_elapsed = time.perf_counter() - db_start
    latencies["db_latency_ms"] = max(db_elapsed * 1000, 0.0)
    record_health_probe("db", db_status, db_elapsed)

    cache_status = "disabled"
    cache_start = time.perf_counter()
    try:
        cache_backend = get_cache()
        if getattr(cache_backend, "enabled", False):
            probe_key = f"healthz:{uuid.uuid4().hex}"
            try:
                await cache_backend.set(probe_key, {"status": "ok"}, ttl=5)
                cache_status = "ok"
            except Exception:
                cache_status = "error"
            finally:
                try:
                    await cache_backend.invalidate(probe_key)
                except Exception:
                    cache_status = "error"
        else:
            cache_status = "disabled"
    except Exception:
        cache_status = "error"
    cache_elapsed = time.perf_counter() - cache_start
    statuses["cache"] = cache_status
    latencies["cache_latency_ms"] = max(cache_elapsed * 1000, 0.0)
    record_health_probe("cache", cache_status, cache_elapsed)

    storage_status, storage_elapsed = await _probe_storage()
    statuses["storage"] = storage_status
    latencies["storage_latency_ms"] = max(storage_elapsed * 1000, 0.0)
    record_health_probe("storage", storage_status, storage_elapsed)

    scanner_start = time.perf_counter()
    if getattr(settings, "event_file_scanner_enabled", False):
        scanner_status = "ok"
        try:
            await check_file_scanner_health()
        except Exception:
            scanner_status = "error"
    else:
        scanner_status = "disabled"
    scanner_elapsed = time.perf_counter() - scanner_start
    statuses["file_scanner"] = scanner_status
    latencies["file_scanner_latency_ms"] = max(scanner_elapsed * 1000, 0.0)
    record_health_probe("file_scanner", scanner_status, scanner_elapsed)

    overall_ok = all(value != "error" for value in statuses.values())
    http_status = (
        status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    # Add pool health metrics
    pool_metrics = get_pool_health_metrics()

    payload = {
        "status": "ok" if overall_ok else "error",
        **statuses,
        **latencies,
        "pool": pool_metrics,
    }

    _health_cache.update(
        {
            "expires_at": now + 5.0,
            "payload": payload,
            "status_code": http_status,
        }
    )
    return JSONResponse(status_code=http_status, content=payload)


@router.get("/ready")
async def ready() -> dict[str, str]:
    await wait_db(max_attempts=1, delay=0.1)
    return {"status": "ready"}
