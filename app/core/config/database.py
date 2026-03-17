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


class DatabaseSettings(BaseAppSettings):
    database_url: str
    database_read_replica_url: str | None = None  # Optional read replica URL

    # Auto-tuning pool size based on CPU cores if not explicitly set
    # Formula: (CPU_COUNT * 2) + 1
    database_pool_size: int = (os.cpu_count() or 1) * 2 + 1
    database_max_overflow: int = (os.cpu_count() or 1) * 4
    database_pool_timeout: float = 30.0
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
