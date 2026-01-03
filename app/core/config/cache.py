from __future__ import annotations

from functools import cached_property
from pydantic import field_validator
from .base import (
    BaseAppSettings,
    _coerce_int_list,
    _coerce_str_list,
    _validate_positive_int,
    _validate_non_negative_int,
)


class CacheSettings(BaseAppSettings):
    cache_backend: str = "redis"
    cache_enabled: bool = True
    cache_redis_url: str = "redis://127.0.0.1:6379/0"
    taskiq_broker_url: str = "redis://127.0.0.1:6379/1"
    session_storage_backend: str = "redis"
    cache_default_ttl_seconds: int = 300
    stats_cache_ttl_seconds: int = 180
    cache_l1_ttl_seconds: int = 60
    cache_warmup_enabled: bool = False
    cache_warmup_groups: list[int] | str = ""
    cache_warmup_stats_users: list[int] | str = ""
    cache_warmup_periods: list[str] | str = "30d,90d"
    cache_warmup_max_age_seconds: int = 120

    @field_validator("stats_cache_ttl_seconds")
    @classmethod
    def _validate_stats_cache_ttl_seconds(cls, value: int) -> int:
        return _validate_positive_int(value, label="STATS_CACHE_TTL_SECONDS")

    @field_validator("cache_backend")
    @classmethod
    def _validate_cache_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"redis", "memory", "tiered", "none"}:
            raise ValueError("CACHE_BACKEND must be redis, memory, tiered, or none")
        return normalized

    @field_validator("cache_warmup_max_age_seconds")
    @classmethod
    def _validate_cache_warmup_max_age(cls, value: int) -> int:
        return _validate_non_negative_int(value, label="CACHE_WARMUP_MAX_AGE_SECONDS")

    @cached_property
    def cache_backend_normalized(self) -> str:
        return self.cache_backend.strip().lower()

    @cached_property
    def cache_warmup_group_ids(self) -> tuple[int, ...]:
        return tuple(_coerce_int_list(self.cache_warmup_groups))

    @cached_property
    def cache_warmup_stats_user_ids(self) -> tuple[int, ...]:
        return tuple(_coerce_int_list(self.cache_warmup_stats_users))

    @cached_property
    def cache_warmup_period_keys(self) -> tuple[str, ...]:
        normalized = [
            item.strip().lower() for item in _coerce_str_list(self.cache_warmup_periods)
        ]
        unique: list[str] = []
        seen: set[str] = set()
        for item in normalized:
            if not item or item in seen:
                continue
            seen.add(item)
            unique.append(item)
        return tuple(unique)
