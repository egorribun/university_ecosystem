from __future__ import annotations

import asyncio
import time
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine, get_pool_health_metrics, wait_db
from app.core.metrics import record_health_probe
from app.deps.cache import get_cache
from app.services.file_scanner import (
    check_file_scanner_health,
    scan_for_malware,  # noqa: F401 - imported for test mocking
)
from app.utils.files import _get_storage_backend
from app.utils.migrations import migrations_are_current

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

router = APIRouter(tags=["health"])

# MOD-06 (audit 2026-03-15 Wave 7): Shutdown flag for K8s graceful drain.
# Set during lifespan shutdown so /health/ready returns 503 while K8s
# removes the pod from service endpoints before SIGKILL.
#
# K8s graceful shutdown timeline:
#   1. SIGTERM received → lifespan shutdown calls set_shutdown_flag()
#   2. K8s readiness probe hits /health/ready → 503 → removes pod from LB
#   3. preStop hook: sleep 5s (in-flight requests from LB drain)
#   4. Remaining requests complete within terminationGracePeriodSeconds
#   5. SIGKILL if process still alive after grace period
_shutdown_flag: asyncio.Event = asyncio.Event()


def set_shutdown_flag() -> None:
    """Signal that this pod is shutting down. Called from lifespan shutdown."""
    if settings.environment == "testing":
        return
    _shutdown_flag.set()


def reset_shutdown_flag() -> None:
    """Reset the shutdown flag. Used primarily in test suites."""
    _shutdown_flag.clear()


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
    """Perform a lightweight existence check on the storage backend."""
    from app.services.storage import StorageBackend

    if not isinstance(backend, StorageBackend):
        return None

    # Use a well-known path or root to check availability
    # For S3, exists("/") usually checks bucket connectivity/existence
    # For local FS, it checks the base_dir
    try:
        exists = await backend.exists("/")
        return "ok" if exists else "error"
    except Exception:  # RZ-22-01-JUSTIFIED: health probe — storage probe returns "error" on any failure (reviewed TD-27-04)
        return "error"


async def _write_delete_storage_probe(backend: Any) -> str:
    probe_name = f"healthz/{uuid.uuid4().hex}.txt"
    try:
        probe_url = await backend.save_file(probe_name, b"", content_type="text/plain")
    except Exception:  # RZ-22-01-JUSTIFIED: health probe — write probe returns "error" on any failure (reviewed TD-27-04)
        return "error"
    try:
        await backend.delete_file(probe_url)
    except Exception:  # RZ-22-01-JUSTIFIED: health probe — delete probe returns "error" on any failure (reviewed TD-27-04)
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
    except Exception:  # RZ-22-01-JUSTIFIED: health probe — storage probe returns "error" on any failure (reviewed TD-27-04)
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


@router.get("/health/live", summary="Liveness Probe")
async def liveness() -> dict[str, str]:
    # MOD-06 (audit 2026-03-15 Wave 7): Liveness probe MUST NOT check
    # external dependencies.  If the DB is down and K8s restarts all pods,
    # the restart cascade worsens the outage.  Liveness = "is the process
    # alive and not deadlocked?" — the answer is always 200 if we reach here.
    return {"status": "alive"}


@router.get("/healthz", summary="Full Health Check")
async def healthz(
    # LOW-W19: brief=True omits migration versions, pool internals, and latency
    # details from the response — use this for public/external health checks to
    # avoid leaking infrastructure details.  Internal/ops dashboards should use
    # the default brief=False to retain full diagnostic information.
    brief: bool = False,
) -> JSONResponse:
    now = time.monotonic()
    if _health_cache["expires_at"] > now:
        return JSONResponse(
            status_code=_health_cache["status_code"],
            content=_health_cache["payload"],
        )

    # PERF-22-02 (audit 2026-03-25 Wave 22): Per-subsystem timeout (5 s) so a
    # single slow probe (e.g. hung DB) cannot block the entire health check
    # and cause cascading readiness failures in the K8s cluster.
    _PROBE_TIMEOUT_SECONDS: float = 5.0

    statuses: dict[str, Any] = {}
    latencies: dict[str, float] = {}

    db_status = "ok"
    db_start = time.perf_counter()
    try:
        async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
            async with engine.connect() as conn:
                # 1. Connectivity check
                await conn.execute(text("SELECT 1"))

                # 2. Migrations check
                is_test = settings.environment in ("testing", "test")
                if is_test:
                    statuses["db_migrations"] = "skipped"
                else:
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
                            statuses["db_migrations_expected"] = sorted(
                                expected_versions
                            )
                            db_status = "error"
                        else:
                            statuses["db_migrations"] = "ok"
                    except Exception:  # RZ-22-01-JUSTIFIED: health probe — migration check failure (reviewed TD-27-04)
                        db_status = "error"
                        statuses["db_migrations"] = "error"

                # 3. Queue status
                queue_status = "ok"
                queue_start = time.perf_counter()
                try:
                    await _check_queue(conn)
                except Exception:  # RZ-25-01  # RZ-22-01-JUSTIFIED: health probe catch-all (reviewed TD-27-04)
                    queue_status = "error"
                queue_elapsed = time.perf_counter() - queue_start
                statuses["notification_queue"] = queue_status
                latencies["notification_queue_latency_ms"] = max(
                    queue_elapsed * 1000, 0.0
                )
                record_health_probe("notification_queue", queue_status, queue_elapsed)

    except TimeoutError:
        db_status = "error"
    except Exception:  # RZ-22-01-JUSTIFIED: health probe — DB probe returns "error" on any failure (reviewed TD-27-04)
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
        async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):  # PERF-22-02
            cache_backend = get_cache()
            if getattr(cache_backend, "enabled", False):
                probe_key = f"healthz:{uuid.uuid4().hex}"
                try:
                    await cache_backend.set(probe_key, {"status": "ok"}, ttl=5)
                    cache_status = "ok"
                except Exception:  # RZ-22-01-JUSTIFIED: health probe — cache set probe returns "error" (reviewed TD-27-04)
                    cache_status = "error"
                finally:
                    try:
                        await cache_backend.invalidate(probe_key)
                    except Exception:  # RZ-22-01-JUSTIFIED: health probe — cache invalidate probe returns "error" (reviewed TD-27-04)
                        cache_status = "error"
            else:
                cache_status = "disabled"
    except TimeoutError:
        cache_status = "error"
    except Exception:  # RZ-22-01-JUSTIFIED: health probe — cache probe returns "error" on any failure (reviewed TD-27-04)
        cache_status = "error"
    cache_elapsed = time.perf_counter() - cache_start
    statuses["cache"] = cache_status
    latencies["cache_latency_ms"] = max(cache_elapsed * 1000, 0.0)
    record_health_probe("cache", cache_status, cache_elapsed)

    storage_start = time.perf_counter()
    try:
        async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):  # PERF-22-02
            storage_status, storage_elapsed = await _probe_storage()
    except TimeoutError:
        storage_status = "error"
        storage_elapsed = time.perf_counter() - storage_start
    statuses["storage"] = storage_status
    latencies["storage_latency_ms"] = max(storage_elapsed * 1000, 0.0)
    record_health_probe("storage", storage_status, storage_elapsed)

    scanner_start = time.perf_counter()
    try:
        async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):  # PERF-22-02
            if getattr(settings, "event_file_scanner_enabled", False):
                scanner_status = "ok"
                try:
                    await check_file_scanner_health()
                except Exception:  # RZ-22-01-JUSTIFIED: health probe — scanner probe returns "error" (reviewed TD-27-04)
                    scanner_status = "error"
            else:
                scanner_status = "disabled"
    except TimeoutError:
        scanner_status = "error"
    scanner_elapsed = time.perf_counter() - scanner_start
    statuses["file_scanner"] = scanner_status
    latencies["file_scanner_latency_ms"] = max(scanner_elapsed * 1000, 0.0)
    record_health_probe("file_scanner", scanner_status, scanner_elapsed)

    # SpiceDB check (RZ-05, audit 2026-03-19)
    from app.core.health import check_spicedb_health

    try:
        async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):  # PERF-22-02
            authz_status, authz_latency_ms = await check_spicedb_health()
    except TimeoutError:
        authz_status = "error"
        authz_latency_ms = _PROBE_TIMEOUT_SECONDS * 1000
    statuses["spicedb"] = authz_status
    latencies["spicedb_latency_ms"] = authz_latency_ms
    record_health_probe("spicedb", authz_status, authz_latency_ms / 1000.0)

    overall_ok = all(value != "error" for value in statuses.values())
    http_status = (
        status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    # Add pool health metrics
    pool_metrics = get_pool_health_metrics()

    full_payload = {
        "status": "ok" if overall_ok else "error",
        **statuses,
        **latencies,
        "pool": pool_metrics,
    }

    _health_cache.update(
        {
            "expires_at": now + 5.0,
            "payload": full_payload,
            "status_code": http_status,
        }
    )

    if brief:
        # LOW-W19: brief mode omits migration version sets, latency details, and
        # pool internals to avoid exposing infrastructure information to external
        # callers.  Only the top-level component statuses and overall status are
        # returned.
        _BRIEF_OMIT_KEYS = frozenset(
            {
                "db_migrations_current",
                "db_migrations_expected",
                "pool",
            }
            | {k for k in full_payload if k.endswith("_latency_ms")}
        )
        brief_payload = {
            k: v for k, v in full_payload.items() if k not in _BRIEF_OMIT_KEYS
        }
        return JSONResponse(status_code=http_status, content=brief_payload)

    return JSONResponse(status_code=http_status, content=full_payload)


@router.get("/ready", summary="Legacy Readiness Check")
@router.get("/health/ready", summary="Readiness Probe")
async def ready() -> dict[str, str]:
    # MOD-06 (audit 2026-03-15 Wave 7): Return 503 immediately during shutdown
    # so K8s removes this pod from the service endpoints before killing it.
    # This prevents new requests from arriving on a terminating pod.
    if _shutdown_flag.is_set():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Shutting down",
        )
    await wait_db(max_attempts=1)
    return {"status": "ready"}
