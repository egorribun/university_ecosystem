from __future__ import annotations

from functools import cached_property

from pydantic import field_validator

from .base import (
    BaseAppSettings,
    _coerce_int_list,
    _coerce_str_list,
    _load_file_secret,
    _validate_non_negative_int,
    _validate_positive_int,
)

DEFAULT_REVOCATION_REDIS_URL = "redis://127.0.0.1:6380/0"


class CacheSettings(BaseAppSettings):
    cache_backend: str = "redis"
    cache_enabled: bool = True
    cache_redis_url: str = "redis://127.0.0.1:6379/0"
    # Security state must use a distinct durable/noeviction Redis process.
    revocation_redis_url: str = DEFAULT_REVOCATION_REDIS_URL
    nats_url: str = "nats://127.0.0.1:4222"
    nats_auth_token: str | None = None
    cache_nats_bucket: str = "ue_cache"
    cache_nats_ttl_seconds: int = 3600
    session_storage_backend: str = "redis"
    cache_default_ttl_seconds: int = 300
    stats_cache_ttl_seconds: int = 180
    cache_l1_ttl_seconds: int = 60
    cache_warmup_enabled: bool = False
    cache_warmup_groups: list[int] | str = ""
    cache_warmup_stats_users: list[int] | str = ""
    cache_warmup_periods: list[str] | str = "30d,90d"
    cache_warmup_max_age_seconds: int = 120

    # ── Per-cache granular tuning ─────────────────────────────────────────────
    # Env vars: CACHE_USER_MAX_SIZE, CACHE_USER_TTL_S, etc.
    # Defaults mirror the previous hardcoded values so behaviour is unchanged.
    cache_user_max_size: int = 500
    cache_user_ttl_s: float = 60.0
    cache_config_max_size: int = 100
    cache_config_ttl_s: float = 300.0
    cache_news_l1_max_size: int = 200
    cache_news_l1_ttl_s: float = 60.0
    cache_news_l2_ttl_s: float = 3600.0
    cache_schedule_l1_max_size: int = 100
    cache_schedule_l1_ttl_s: float = 120.0
    cache_schedule_l2_ttl_s: float = 7200.0

    @field_validator("nats_auth_token", mode="before")
    @classmethod
    def _load_nats_token_from_file(cls, v: str | None) -> str | None:
        # RZ-05 (audit Wave 12): support NATS_AUTH_TOKEN_FILE=/run/secrets/nats_auth_token.
        return _load_file_secret("NATS_AUTH_TOKEN_FILE", v)

    @field_validator("stats_cache_ttl_seconds")
    @classmethod
    def _validate_stats_cache_ttl_seconds(cls, value: int) -> int:
        return _validate_positive_int(value, label="STATS_CACHE_TTL_SECONDS")

    @field_validator("cache_backend")
    @classmethod
    def _validate_cache_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"redis", "memory", "tiered", "none", "nats"}:
            raise ValueError(
                "CACHE_BACKEND must be redis, memory, tiered, none, or nats"
            )
        return normalized

    @field_validator("revocation_redis_url")
    @classmethod
    def _validate_revocation_redis_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("REVOCATION_REDIS_URL must not be empty")
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
