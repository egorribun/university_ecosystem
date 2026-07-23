from __future__ import annotations

import builtins
import io
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import database


def test_cgroup_cpu_count_prefers_affinity(monkeypatch):
    monkeypatch.setattr(
        database.os, "sched_getaffinity", lambda _: {1, 2, 3}, raising=False
    )
    assert database._cgroup_aware_cpu_count() == 3


def test_cgroup_cpu_count_uses_positive_v1_quota(monkeypatch):
    def unavailable(_):
        raise NotImplementedError

    values = iter((io.StringIO("8"), io.StringIO("2")))
    monkeypatch.setattr(database.os, "sched_getaffinity", unavailable, raising=False)
    monkeypatch.setattr(builtins, "open", lambda *args, **kwargs: next(values))
    assert database._cgroup_aware_cpu_count() == 4


def test_cgroup_cpu_count_caps_large_quota(monkeypatch):
    monkeypatch.setattr(
        database.os,
        "sched_getaffinity",
        lambda _: (_ for _ in ()).throw(NotImplementedError),
        raising=False,
    )
    values = iter((io.StringIO("128"), io.StringIO("1")))
    monkeypatch.setattr(builtins, "open", lambda *args, **kwargs: next(values))
    assert database._cgroup_aware_cpu_count() == 32


def test_cgroup_cpu_count_falls_back_after_invalid_or_unavailable_cgroup(monkeypatch):
    monkeypatch.delattr(database.os, "sched_getaffinity", raising=False)
    monkeypatch.setattr(
        builtins,
        "open",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError),
    )
    monkeypatch.setattr(database.os, "cpu_count", lambda: 7)
    assert database._cgroup_aware_cpu_count() == 7

    values = iter((io.StringIO("0"), io.StringIO("1")))
    monkeypatch.setattr(builtins, "open", lambda *args, **kwargs: next(values))
    monkeypatch.setattr(database.os, "cpu_count", lambda: 5)
    assert database._cgroup_aware_cpu_count() == 5

    monkeypatch.setattr(
        builtins,
        "open",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError),
    )
    monkeypatch.setattr(database.os, "cpu_count", lambda: None)
    assert database._cgroup_aware_cpu_count() == 2


def test_database_url_file_loading(monkeypatch):
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as handle:
        handle.write("  sqlite+aiosqlite:///from-file.db  \n")
        path = Path(handle.name)
    monkeypatch.setenv("DATABASE_URL_FILE", str(path))
    try:
        settings = database.DatabaseSettings(database_url="fallback")
        assert settings.database_url == "sqlite+aiosqlite:///from-file.db"
    finally:
        path.unlink(missing_ok=True)


def test_database_settings_valid_values_and_validators():
    settings = database.DatabaseSettings(
        database_url="sqlite+aiosqlite:///./test.db",
        database_pool_size=3,
        database_max_overflow=0,
        database_pool_timeout=1.5,
        database_pool_recycle=0,
        slow_query_threshold_ms=0.5,
    )
    assert settings.database_pool_size == 3
    assert settings.database_read_replica_url is None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("database_pool_size", 0, "DATABASE_POOL_SIZE"),
        ("database_max_overflow", -1, "DATABASE_MAX_OVERFLOW"),
        ("database_pool_timeout", 0, "DATABASE_POOL_TIMEOUT"),
        ("database_pool_recycle", -1, "DATABASE_POOL_RECYCLE"),
        ("slow_query_threshold_ms", 0, "SLOW_QUERY_THRESHOLD_MS"),
    ),
)
def test_database_settings_reject_invalid_values(field, value, message):
    with pytest.raises(ValidationError, match=message):
        database.DatabaseSettings(
            database_url="sqlite+aiosqlite:///./test.db", **{field: value}
        )
