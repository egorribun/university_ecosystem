from __future__ import annotations

from pydantic import field_validator

from .base import (
    BaseAppSettings,
    _validate_non_negative_int,
    _validate_positive_float,
    _validate_positive_int,
)


class DatabaseSettings(BaseAppSettings):
    database_url: str
    database_read_replica_url: str | None = None  # Optional read replica URL
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout: float = 30.0
    database_pool_recycle: int = 1_800

    # Slow query logging configuration
    slow_query_logging_enabled: bool = True
    slow_query_threshold_ms: float = 500.0  # 500ms for production
    slow_query_explain_enabled: bool = False  # Enable EXPLAIN for slow queries

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
