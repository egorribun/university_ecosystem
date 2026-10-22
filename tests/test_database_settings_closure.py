from __future__ import annotations

import builtins
import io
import re
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


def test_cgroup_cpu_count_uses_string_affinity_attribute_lookup(monkeypatch):
    """The optional affinity lookup must use the real attribute name."""
    monkeypatch.setattr(
        builtins,
        "open",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError),
    )
    monkeypatch.setattr(
        database.os, "sched_getaffinity", lambda _: {1, 2, 3, 4}, raising=False
    )

    assert database._cgroup_aware_cpu_count() == 4


def test_cgroup_cpu_count_uses_explicit_none_for_optional_affinity_lookup(monkeypatch):
    """The optional affinity lookup must retain its explicit fail-safe default."""
    monkeypatch.setattr(
        builtins,
        "open",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError),
    )
    monkeypatch.setattr(
        database.os, "sched_getaffinity", lambda _: {1, 2, 3, 4, 5}, raising=False
    )
    calls: list[tuple[object, str, object]] = []

    def lookup(obj: object, name: str, default: object) -> object:
        calls.append((obj, name, default))
        return builtins.getattr(obj, name, default)

    # Replacing the module's builtin lookup makes omission of the third
    # argument observable instead of equivalent on hosts exposing the method.
    monkeypatch.setattr(database, "getattr", lookup, raising=False)

    assert database._cgroup_aware_cpu_count() == 5
    assert calls == [(database.os, "sched_getaffinity", None)]


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


@pytest.mark.parametrize(
    ("document", "heading", "defaults_marker"),
    (
        (
            "DEPLOY.md",
            "### Пул соединений базы данных",
            "Значения по умолчанию",
        ),
        (
            "DEPLOY.en.md",
            "### Database connection pool",
            "Default values",
        ),
    ),
)
def test_deployment_pool_defaults_match_database_settings(
    document, heading, defaults_marker
):
    path = Path(__file__).resolve().parents[1] / "docs" / document
    text = path.read_text(encoding="utf-8")
    assert text.count(heading) == 1
    section = text.split(heading, 1)[1].split("\n### ", 1)[0]
    defaults = [line for line in section.splitlines() if defaults_marker in line]
    assert len(defaults) == 1

    fields = database.DatabaseSettings.model_fields
    assert fields["database_pool_size"].default == database._CPU_COUNT * 2 + 1
    assert fields["database_max_overflow"].default == database._CPU_COUNT * 4

    documented_defaults = re.findall(
        r"`([^`]+)`", defaults[0].split(defaults_marker, 1)[1]
    )
    assert documented_defaults == [
        "_CPU_COUNT * 2 + 1",
        "_CPU_COUNT * 4",
        format(fields["database_pool_timeout"].default, "g"),
        format(fields["database_pool_recycle"].default, "g"),
    ]


@pytest.mark.parametrize(
    ("document", "heading", "example_marker", "defaults_marker"),
    (
        (
            "DEPLOY.md",
            "### Пул соединений базы данных",
            "Например",
            "Значения по умолчанию",
        ),
        (
            "DEPLOY.en.md",
            "### Database connection pool",
            "For example",
            "Default values",
        ),
    ),
)
def test_deployment_pool_override_example_remains_explicit(
    document, heading, example_marker, defaults_marker
):
    path = Path(__file__).resolve().parents[1] / "docs" / document
    text = path.read_text(encoding="utf-8")
    assert text.count(heading) == 1
    section = text.split(heading, 1)[1].split("\n### ", 1)[0]
    examples = [line for line in section.splitlines() if example_marker in line]
    assert len(examples) == 1
    assert "`DATABASE_POOL_SIZE=5`" in examples[0]
    assert "`DATABASE_MAX_OVERFLOW=5`" in examples[0]
    assert defaults_marker not in examples[0]
