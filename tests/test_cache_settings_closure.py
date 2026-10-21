from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config.cache import CacheSettings


def test_cache_backend_validator_accepts_all_modes_and_normalizes():
    for backend in ("redis", "memory", "tiered", "none", "nats"):
        settings = CacheSettings(cache_backend=f"  {backend.upper()}  ")
        assert settings.cache_backend == backend
        assert settings.cache_backend_normalized == backend


def test_cache_backend_validator_rejects_unknown_mode():
    with pytest.raises(ValidationError, match="CACHE_BACKEND must be"):
        CacheSettings(cache_backend="filesystem")


def test_revocation_redis_url_validator_rejects_blank_value():
    with pytest.raises(ValidationError, match="REVOCATION_REDIS_URL must not be empty"):
        CacheSettings(revocation_redis_url="   ")


def test_cache_ttl_validators_reject_invalid_values():
    with pytest.raises(ValidationError, match="STATS_CACHE_TTL_SECONDS"):
        CacheSettings(stats_cache_ttl_seconds=0)
    with pytest.raises(ValidationError, match="CACHE_WARMUP_MAX_AGE_SECONDS"):
        CacheSettings(cache_warmup_max_age_seconds=-1)


@pytest.mark.parametrize(
    "field",
    (
        "cache_user_max_size",
        "cache_config_max_size",
        "cache_news_l1_max_size",
        "cache_schedule_l1_max_size",
    ),
)
@pytest.mark.parametrize("value", (0, -1))
def test_cache_l1_capacity_rejects_non_positive_values(field, value):
    with pytest.raises(ValidationError, match="greater than zero"):
        CacheSettings(**{field: value})


@pytest.mark.parametrize(
    "field",
    (
        "cache_user_max_size",
        "cache_config_max_size",
        "cache_news_l1_max_size",
        "cache_schedule_l1_max_size",
    ),
)
def test_cache_l1_capacity_accepts_positive_boundary(field):
    assert getattr(CacheSettings(**{field: 1}), field) == 1


def test_nats_auth_token_file_is_loaded(monkeypatch):
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as handle:
        handle.write("  token-from-file  \n")
        token_file = Path(handle.name)
    monkeypatch.setenv("NATS_AUTH_TOKEN_FILE", str(token_file))
    try:
        assert (
            CacheSettings(nats_auth_token="fallback").nats_auth_token
            == "token-from-file"
        )
    finally:
        token_file.unlink(missing_ok=True)


def test_nats_auth_token_file_errors_are_validation_errors(monkeypatch):
    missing_file = Path(tempfile.gettempdir()) / f"missing-{uuid.uuid4()}"
    monkeypatch.setenv("NATS_AUTH_TOKEN_FILE", str(missing_file))
    with pytest.raises(ValidationError, match="NATS_AUTH_TOKEN_FILE"):
        CacheSettings(nats_auth_token="fallback")


def test_cache_warmup_properties_coerce_and_deduplicate_values():
    first_group, second_group = uuid.uuid4(), uuid.uuid4()
    first_user, second_user = uuid.uuid4(), uuid.uuid4()
    settings = CacheSettings(
        cache_warmup_groups=f"{first_group}, bad, {second_group}, {first_group}",
        cache_warmup_stats_users=f"{first_user},invalid,{second_user}",
        cache_warmup_periods="30D, 90d, , 30d, 7D",
    )
    assert settings.cache_warmup_group_ids == (first_group, second_group, first_group)
    assert settings.cache_warmup_stats_user_ids == (first_user, second_user)
    assert settings.cache_warmup_period_keys == ("30d", "90d", "7d")


def test_cache_warmup_properties_handle_empty_and_iterable_inputs():
    settings = CacheSettings(
        cache_warmup_groups=[],
        cache_warmup_stats_users=[],
        cache_warmup_periods=[],
    )
    assert settings.cache_warmup_group_ids == ()
    assert settings.cache_warmup_stats_user_ids == ()
    assert settings.cache_warmup_period_keys == ()


def test_cache_warmup_properties_preserve_uuid_ids_and_skip_invalid_tokens():
    group_ids = (uuid.uuid4(), uuid.uuid4())
    user_id = uuid.uuid4()
    settings = CacheSettings(
        cache_warmup_groups=f"{group_ids[0]},not-a-uuid,{group_ids[1]},{group_ids[0]}",
        cache_warmup_stats_users=f"{user_id},invalid",
    )

    assert settings.cache_warmup_group_ids == (*group_ids, group_ids[0])
    assert settings.cache_warmup_stats_user_ids == (user_id,)


@pytest.mark.parametrize("as_json", [False, True], ids=["csv", "json-list"])
def test_cache_warmup_uuid_ids_load_from_environment(monkeypatch, as_json):
    group_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    user_ids = [str(uuid.uuid4())]
    group_value = json.dumps(group_ids) if as_json else ",".join(group_ids)
    user_value = json.dumps(user_ids) if as_json else ",".join(user_ids)
    monkeypatch.setenv("CACHE_WARMUP_GROUPS", group_value)
    monkeypatch.setenv("CACHE_WARMUP_STATS_USERS", user_value)

    settings = CacheSettings(_env_file=None)

    assert settings.cache_warmup_group_ids == tuple(map(uuid.UUID, group_ids))
    assert settings.cache_warmup_stats_user_ids == tuple(map(uuid.UUID, user_ids))
