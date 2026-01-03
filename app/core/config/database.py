from __future__ import annotations

from pydantic import field_validator
from .base import BaseAppSettings, _validate_positive_int, _validate_non_negative_int, _validate_positive_float


class DatabaseSettings(BaseAppSettings):
    database_url: str
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout: float = 30.0
    database_pool_recycle: int = 1_800

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
