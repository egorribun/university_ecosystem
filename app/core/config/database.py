from __future__ import annotations

import os

from pydantic import field_validator

from .base import (
    BaseAppSettings,
    _load_file_secret,
    _validate_non_negative_int,
    _validate_positive_float,
    _validate_positive_int,
)


def _cgroup_aware_cpu_count() -> int:
    """Return cgroup-aware CPU count for container environments.

    RZ-20-03 (audit 2026-03-24): ``os.cpu_count()`` returns the **host** CPU
    count inside containers.  On a 32-core host with a 2-CPU container limit
    the old formula produced ``pool_size = 65`` and ``max_overflow = 128``,
    easily exhausting PostgreSQL's ``max_connections`` (default 100).

    Detection order is quota-first so a Docker/Kubernetes ``--cpus`` limit is
    honoured even when the process still has access to every host CPU through
    ``sched_getaffinity`` (the common cgroups v2 configuration):

    1. ``/sys/fs/cgroup/cpu.max`` — cgroups v2 quota/period pair.
    2. ``/sys/fs/cgroup/cpu/cpu.cfs_quota_us`` and ``cpu.cfs_period_us`` —
       cgroups v1 (legacy Docker).
    3. ``os.sched_getaffinity(0)`` — cpuset/host affinity fallback.
    4. ``os.cpu_count()`` — bare-metal fallback.

    ``app.auth.security._container_cpu_count()`` delegates to this function so
    database pools and Argon2 workers use the same bounded interpretation.
    """

    # cgroups v2 exposes CPU quota and period in a single file.  ``max`` means
    # no quota; in that case affinity remains the best available signal.  Read
    # this before affinity: cpuset affinity does not reflect ``--cpus`` quotas.
    try:
        with open("/sys/fs/cgroup/cpu.max") as f:
            fields = f.read().strip().split()
        if len(fields) == 2:
            try:
                quota, period = map(int, fields)
            except (TypeError, ValueError):
                pass
            else:
                if quota > 0 and period > 0:
                    return min(max(1, quota // period), 32)
    except (FileNotFoundError, ValueError, OSError):
        pass

    # cgroups v1 stores quota and period separately.  Keep the same cap as the
    # v2 path so malformed or unexpectedly large host values cannot over-size
    # connection pools or CPU-bound executors.
    try:
        with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us") as f:
            quota = int(f.read().strip())
        with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us") as f:
            period = int(f.read().strip())
        if quota > 0 and period > 0:
            return min(max(1, quota // period), 32)
    except (FileNotFoundError, ValueError, OSError):
        pass

    try:
        if hasattr(os, "sched_getaffinity"):
            sched = os.sched_getaffinity
        else:
            sched = None
        if sched:
            return len(sched(0))
    except (AttributeError, NotImplementedError, OSError):
        pass
    return os.cpu_count() or 2


_CPU_COUNT: int = _cgroup_aware_cpu_count()


class DatabaseSettings(BaseAppSettings):
    database_url: str
    database_read_replica_url: str | None = None  # Optional read replica URL

    # RZ-20-03 (audit 2026-03-24): Use cgroup-aware CPU count instead of
    # os.cpu_count() which returns the HOST core count inside containers.
    # Formula: (CPU_COUNT * 2) + 1 — standard for I/O-bound web workers.
    database_pool_size: int = _CPU_COUNT * 2 + 1
    database_max_overflow: int = _CPU_COUNT * 4
    database_pool_timeout: float = 30.0

    # RZ-20-06 (audit 2026-03-24): Configurable asyncpg statement cache.
    # Set to 0 when using PgBouncer/Odyssey in transaction pooling mode
    # (prepared statements are connection-scoped; PgBouncer reuses server
    # connections across clients causing "prepared statement does not exist").
    # Set to 1024 (asyncpg default) for direct PostgreSQL connections to
    # avoid ~10-20% parsing overhead on every query.
    database_statement_cache_size: int = 0
    # PERF-W9-05: Reduced from 1800 (30 min) to 540 (9 min).
    # Most managed PostgreSQL providers (RDS, Cloud SQL, Supabase) close idle
    # connections after ~10 minutes.  With a 30-min recycle, low-traffic periods
    # (e.g. overnight) cause pool connections to be silently severed by the
    # provider before they're recycled, triggering asyncpg.ConnectionDoesNotExistError
    # on the first request after the idle gap.  9 minutes is safely under the
    # 10-minute threshold.  pool_pre_ping=True (set in database.py) provides an
    # additional belt-and-suspenders health check at checkout time.
    database_pool_recycle: int = 540

    # Slow query logging configuration
    slow_query_logging_enabled: bool = True
    slow_query_threshold_ms: float = 500.0  # 500ms for production
    slow_query_explain_enabled: bool = False  # Enable EXPLAIN for slow queries

    @field_validator("database_url", mode="before")
    @classmethod
    def _load_database_url_from_file(cls, v: str | None) -> str | None:
        # RZ-05 (audit Wave 12): support DATABASE_URL_FILE=/run/secrets/database_url
        # so the connection string (including password) never appears in docker inspect.
        return _load_file_secret("DATABASE_URL_FILE", v)

    @field_validator("database_pool_size")
    @classmethod
    def _validate_database_pool_size(cls, value: int) -> int:
        return _validate_positive_int(value, label="DATABASE_POOL_SIZE")

    @field_validator("database_max_overflow")
    @classmethod
    def _validate_database_max_overflow(cls, value: int) -> int:
        return _validate_non_negative_int(value, label="DATABASE_MAX_OVERFLOW")

    @field_validator("database_pool_timeout")
    @classmethod
    def _validate_database_pool_timeout(cls, value: float) -> float:
        return _validate_positive_float(value, label="DATABASE_POOL_TIMEOUT")

    @field_validator("database_pool_recycle")
    @classmethod
    def _validate_database_pool_recycle(cls, value: int) -> int:
        return _validate_non_negative_int(value, label="DATABASE_POOL_RECYCLE")

    @field_validator("slow_query_threshold_ms")
    @classmethod
    def _validate_slow_query_threshold(cls, value: float) -> float:
        return _validate_positive_float(value, label="SLOW_QUERY_THRESHOLD_MS")
