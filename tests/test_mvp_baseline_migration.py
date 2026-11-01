"""Unit contract for the squashed MVP baseline revision (Tier 0 migration)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = PROJECT_ROOT / "alembic" / "versions" / "202611020000_mvp_baseline.py"


def _load_baseline() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mvp_baseline_under_test", BASELINE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class _Bind:
    def __init__(self, dialect: str, pg_cron_available: bool) -> None:
        self.dialect = type("Dialect", (), {"name": dialect})()
        self._pg_cron_available = pg_cron_available
        self.queries: list[str] = []

    def execute(self, statement: Any) -> _Result:
        sql = str(statement)
        self.queries.append(sql)
        if "pg_available_extensions" in sql and self._pg_cron_available:
            return _Result((1,))
        return _Result(None)


class _Op:
    def __init__(self, bind: _Bind) -> None:
        self._bind = bind
        self.executed: list[str] = []

    def get_bind(self) -> _Bind:
        return self._bind

    def execute(self, statement: str) -> None:
        self.executed.append(statement)


def test_baseline_revision_is_the_root_of_the_squashed_chain() -> None:
    module = _load_baseline()

    assert module.revision == "202611020000"
    assert module.down_revision is None
    assert module.branch_labels is None
    assert module.depends_on is None


def test_downgrade_is_irreversible_and_refuses_before_changing_schema() -> None:
    module = _load_baseline()

    assert module.downgrade_policy == "irreversible"
    with pytest.raises(RuntimeError) as raised:
        module.downgrade()
    assert str(raised.value) == module.downgrade_reason
    assert "consistent backup" in module.downgrade_reason


def test_upgrade_requires_postgresql_and_executes_nothing_elsewhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_baseline()
    op = _Op(_Bind("sqlite", pg_cron_available=False))
    monkeypatch.setattr(module, "op", op)

    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        module.upgrade()
    assert op.executed == []


def test_upgrade_creates_the_restored_and_delivery_once_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_baseline()
    op = _Op(_Bind("postgresql", pg_cron_available=False))
    monkeypatch.setattr(module, "op", op)

    module.upgrade()

    executed = "\n".join(op.executed)
    assert "CREATE ROLE ue_rls_bypass NOLOGIN" in executed
    assert "CREATE TABLE public.notification_delivery_once" in executed
    assert "uq_notification_delivery_once_claim UNIQUE NULLS NOT DISTINCT" in executed
    for index_name in (
        "ux_users_lower_email",
        "ix_user_profiles_full_name_lower",
        "ix_user_profiles_full_name_trgm",
        "idx_notifications_user_unread_created",
        "idx_messages_chat_created",
        "ix_stored_events_pending",
        "idx_active_sessions_user_valid",
        "ix_active_sessions_user_active_created",
    ):
        assert index_name in executed, index_name
    partitions = [s for s in op.executed if "PARTITION OF" in s]
    assert len(partitions) == 4 * 26
    assert not any("cron.schedule" in s for s in op.executed)


def test_upgrade_schedules_pg_cron_jobs_only_when_the_extension_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_baseline()
    op = _Op(_Bind("postgresql", pg_cron_available=True))
    monkeypatch.setattr(module, "op", op)

    module.upgrade()

    assert op.executed[-4:] == list(module._PG_CRON_STATEMENTS)
    assert op.executed[-4] == "CREATE EXTENSION IF NOT EXISTS pg_cron"
    assert sum("cron.schedule" in s for s in op.executed) == 3
