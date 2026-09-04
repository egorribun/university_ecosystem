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
        builtins,
        "open",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError),
    )
    monkeypatch.setattr(
        database.os, "sched_getaffinity", lambda _: {1, 2, 3}, raising=False
    )
    assert database._cgroup_aware_cpu_count() == 3


def test_cgroup_cpu_count_prefers_v2_quota_over_host_affinity(monkeypatch):
    def fake_open(path, *args, **kwargs):
        if path == "/sys/fs/cgroup/cpu.max":
            return io.StringIO("200000 100000\n")
        raise FileNotFoundError(path)

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(
        database.os,
        "sched_getaffinity",
        lambda _: set(range(64)),
        raising=False,
    )
    assert database._cgroup_aware_cpu_count() == 2


@pytest.mark.parametrize(
    ("cpu_max", "expected"),
    (
        # A quota smaller than one period still grants one CPU; it must not
        # fall through to the host affinity count.
        ("1 100000\n", 1),
        # A one-microsecond period is valid and exercises the upper cap.
        ("100000 1\n", 32),
        # CPU quotas are integer divisions.  Returning a float would leak into
        # pool-size arithmetic and violate the helper's ``int`` contract.
        ("150000 100000\n", 1),
    ),
)
def test_cgroup_cpu_count_v2_preserves_positive_quota_integer_contract(
    monkeypatch, cpu_max, expected
):
    def fake_open(path, *args, **kwargs):
        if path == "/sys/fs/cgroup/cpu.max":
            return io.StringIO(cpu_max)
        raise FileNotFoundError(path)

    monkeypatch.setattr(builtins, "open", fake_open)
    # Make a quota fallback observably different from each valid quota result.
    monkeypatch.setattr(
        database.os,
        "sched_getaffinity",
        lambda _: set(range(4)),
        raising=False,
    )

    result = database._cgroup_aware_cpu_count()

    assert result == expected
    assert isinstance(result, int)


def test_cgroup_cpu_count_caps_large_v2_quota(monkeypatch):
    def fake_open(path, *args, **kwargs):
        if path == "/sys/fs/cgroup/cpu.max":
            return io.StringIO("6400000 100000\n")
        raise FileNotFoundError(path)

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(
        database.os,
        "sched_getaffinity",
        lambda _: set(range(64)),
        raising=False,
    )
    assert database._cgroup_aware_cpu_count() == 32


@pytest.mark.parametrize(
    "cpu_max",
    (
        "max 100000\n",
        "malformed\n",
        "100000 nope\n",
        "0 100000\n",
        "100000 0\n",
    ),
)
def test_cgroup_cpu_count_v2_unlimited_or_invalid_uses_affinity(monkeypatch, cpu_max):
    def fake_open(path, *args, **kwargs):
        if path == "/sys/fs/cgroup/cpu.max":
            return io.StringIO(cpu_max)
        raise FileNotFoundError(path)

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(
        database.os, "sched_getaffinity", lambda _: {1, 2, 3, 4}, raising=False
    )
    assert database._cgroup_aware_cpu_count() == 4


def test_cgroup_cpu_count_uses_positive_v1_quota(monkeypatch):
    def unavailable(_):
        raise NotImplementedError

    def fake_open(path, *args, **kwargs):
        if path.endswith("cpu.cfs_quota_us"):
            return io.StringIO("8")
        if path.endswith("cpu.cfs_period_us"):
            return io.StringIO("2")
        raise FileNotFoundError(path)

    monkeypatch.setattr(database.os, "sched_getaffinity", unavailable, raising=False)
    monkeypatch.setattr(builtins, "open", fake_open)
    assert database._cgroup_aware_cpu_count() == 4


def test_cgroup_cpu_count_rejects_non_positive_v1_period(monkeypatch):
    """A zero cgroup-v1 period must not produce a quota-derived pool size."""

    def unavailable(_):
        raise NotImplementedError

    def fake_open(path, *args, **kwargs):
        if path.endswith("cpu.cfs_quota_us"):
            return io.StringIO("8")
        if path.endswith("cpu.cfs_period_us"):
            return io.StringIO("0")
        raise FileNotFoundError(path)

    monkeypatch.setattr(database.os, "sched_getaffinity", unavailable, raising=False)
    monkeypatch.setattr(database.os, "cpu_count", lambda: 6)
    monkeypatch.setattr(builtins, "open", fake_open)

    assert database._cgroup_aware_cpu_count() == 6


def test_cgroup_cpu_count_caps_large_quota(monkeypatch):
    monkeypatch.setattr(
        database.os,
        "sched_getaffinity",
        lambda _: (_ for _ in ()).throw(NotImplementedError),
        raising=False,
    )

    def fake_open(path, *args, **kwargs):
        if path.endswith("cpu.cfs_quota_us"):
            return io.StringIO("128")
        if path.endswith("cpu.cfs_period_us"):
            return io.StringIO("1")
        raise FileNotFoundError(path)

    monkeypatch.setattr(builtins, "open", fake_open)
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

    def fake_open_zero(path, *args, **kwargs):
        if path.endswith("cpu.cfs_quota_us"):
            return io.StringIO("0")
        if path.endswith("cpu.cfs_period_us"):
            return io.StringIO("1")
        raise FileNotFoundError(path)

    monkeypatch.setattr(builtins, "open", fake_open_zero)
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
