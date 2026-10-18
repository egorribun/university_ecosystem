"""Live PostgreSQL rendering of changed Alembic revisions for Squawk (AUD-208)."""

from __future__ import annotations

import os
import runpy
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url

from scripts.quality import render_live_alembic_sql as renderer

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ROOT_MIGRATION = _PROJECT_ROOT / "alembic" / "versions" / "b05ae64aaeef_init.py"
_AUD180_MIGRATION = (
    _PROJECT_ROOT
    / "alembic"
    / "versions"
    / "202610120002_add_news_media_asset_ownership.py"
)
_GUARDED_MIGRATION = (
    _PROJECT_ROOT / "alembic" / "versions" / "148642dd1207_fix_missing_tables.py"
)
_LIVE_DATABASE = bool(os.getenv("RUN_INTEGRATION_TESTS"))
_UNREACHABLE_DATABASE_URL = (
    "postgresql+asyncpg://migration-gate@127.0.0.1:9/unreachable"
)


def test_ddl_recorder_preserves_leading_directives_and_lock_copy_order() -> None:
    recorder = renderer._DdlRecorder()
    recorder.active = True
    rename = (
        "-- The source heap remains locked while the replacement takes its name.\n"
        "-- squawk-ignore renaming-table\n"
        "ALTER TABLE public.events RENAME TO events_prepart_old"
    )

    recorder(
        None,
        None,
        "LOCK TABLE public.events IN ACCESS EXCLUSIVE MODE",
        None,
        None,
        False,
    )
    recorder(None, None, rename, None, None, False)
    recorder(
        None,
        None,
        "INSERT INTO public.events SELECT * FROM public.events_prepart_old",
        None,
        None,
        False,
    )

    assert recorder.statements == [
        "LOCK TABLE public.events IN ACCESS EXCLUSIVE MODE",
        rename,
        "INSERT INTO public.events SELECT * FROM public.events_prepart_old",
    ]


def test_ddl_recorder_keeps_parameterized_dml_as_a_non_ddl_comment() -> None:
    recorder = renderer._DdlRecorder()
    recorder.active = True
    statement = "DELETE FROM public.events_default WHERE occurred_at >= %(start)s"
    context = SimpleNamespace(compiled=SimpleNamespace(binds={"start": object()}))

    recorder(None, None, statement, {"start": "secret-value"}, context, False)

    assert len(recorder.statements) == 1
    assert "non-DDL observation only" in recorder.statements[0]
    assert (
        "-- DELETE FROM public.events_default WHERE occurred_at >= %(start)s"
        in (recorder.statements[0])
    )
    assert "secret-value" not in recorder.statements[0]


def test_ddl_recorder_does_not_duplicate_transaction_events_as_cursor_sql() -> None:
    recorder = renderer._DdlRecorder()
    recorder.active = True

    recorder._on_begin(None)
    recorder(None, None, "BEGIN", None, None, False)

    assert recorder.statements == [
        "-- observed SQLAlchemy begin event; transaction-event representation, "
        "not cursor text\nBEGIN"
    ]


class _FakeAdminConnection:
    def __init__(self, statements: list[str]) -> None:
        self.statements = statements

    def __enter__(self) -> _FakeAdminConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def exec_driver_sql(self, statement: str) -> None:
        self.statements.append(statement)


class _FakeAdminEngine:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.disposed = False

    def connect(self) -> _FakeAdminConnection:
        return _FakeAdminConnection(self.statements)

    def dispose(self) -> None:
        self.disposed = True


def _patch_renderer_runtime(
    monkeypatch: pytest.MonkeyPatch,
    fake_upgrade: Callable[[object, str], None],
) -> tuple[_FakeAdminEngine, list[renderer._DdlRecorder]]:
    admin = _FakeAdminEngine()
    recorders: list[renderer._DdlRecorder] = []
    recorder_type = renderer._DdlRecorder

    def new_recorder() -> renderer._DdlRecorder:
        recorder = recorder_type()
        recorders.append(recorder)
        return recorder

    monkeypatch.setattr(renderer, "_connect_admin", lambda _url: admin)
    monkeypatch.setattr(
        renderer,
        "read_revision_metadata",
        lambda _migration: ("target", "parent"),
    )
    monkeypatch.setattr(renderer, "_alembic_config", lambda: object())
    monkeypatch.setattr(renderer, "_DdlRecorder", new_recorder)
    monkeypatch.setattr(renderer.command, "upgrade", fake_upgrade)
    return admin, recorders


def _assert_recorder_listeners_removed(recorder: renderer._DdlRecorder) -> None:
    for event_name, listener in recorder.event_listeners():
        assert not renderer.event.contains(renderer.Engine, event_name, listener)


def test_live_renderer_records_transaction_events_and_removes_listeners_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "postgresql+psycopg://renderer@localhost/university"
    monkeypatch.setenv("DATABASE_URL", database_url)

    def fake_upgrade(_config: object, destination: str) -> None:
        if destination == "parent":
            return
        engine = sa.create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql("CREATE TABLE rendered (id INTEGER)")
        finally:
            engine.dispose()

    admin, recorders = _patch_renderer_runtime(monkeypatch, fake_upgrade)

    sql = renderer.render_revision_sql(Path("target.py"), database_url)

    assert sql.count("BEGIN;") == 1
    assert sql.count("COMMIT;") == 1
    assert "CREATE TABLE rendered (id INTEGER);" in sql
    assert admin.disposed
    assert admin.statements[0].startswith('CREATE DATABASE "alembic_squawk_')
    assert admin.statements[1].startswith('DROP DATABASE IF EXISTS "alembic_squawk_')
    assert os.environ["DATABASE_URL"] == database_url
    _assert_recorder_listeners_removed(recorders[0])


def test_live_renderer_records_rollback_and_removes_listeners_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "postgresql+psycopg://renderer@localhost/university"
    monkeypatch.setenv("DATABASE_URL", database_url)

    def fake_upgrade(_config: object, destination: str) -> None:
        if destination == "parent":
            return
        engine = sa.create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql("CREATE TABLE rendered (id INTEGER)")
                raise RuntimeError("simulated migration failure")
        finally:
            engine.dispose()

    admin, recorders = _patch_renderer_runtime(monkeypatch, fake_upgrade)

    with pytest.raises(RuntimeError, match="simulated migration failure"):
        renderer.render_revision_sql(Path("target.py"), database_url)

    statements = recorders[0].statements
    assert sum(statement.endswith("\nBEGIN") for statement in statements) == 1
    assert sum(statement.endswith("\nROLLBACK") for statement in statements) == 1
    assert not any(statement.endswith("\nCOMMIT") for statement in statements)
    assert admin.disposed
    assert os.environ["DATABASE_URL"] == database_url
    _assert_recorder_listeners_removed(recorders[0])


def test_main_requires_a_migration_and_an_output_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert renderer.main(["only-one-argument"]) == 2
    assert "usage: render_live_alembic_sql.py" in capsys.readouterr().err


def test_main_requires_a_postgresql_database_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./dev.db")

    assert renderer.main([str(_AUD180_MIGRATION), str(tmp_path / "out.sql")]) == 2
    assert "DATABASE_URL must target PostgreSQL" in capsys.readouterr().err


def test_main_rejects_migrations_without_literal_revision_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DATABASE_URL", _UNREACHABLE_DATABASE_URL)
    migration = tmp_path / "dynamic.py"
    migration.write_text("revision = make_revision()\ndown_revision = None\n")

    assert renderer.main([str(migration), str(tmp_path / "out.sql")]) == 2
    assert "revision must be a string literal" in capsys.readouterr().err


def test_admin_connection_is_retried_then_reported_as_unreachable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DATABASE_URL", _UNREACHABLE_DATABASE_URL)
    monkeypatch.setattr(renderer.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(renderer, "_ADMIN_CONNECT_ATTEMPTS", 2)

    assert renderer.main([str(_AUD180_MIGRATION), str(tmp_path / "out.sql")]) == 2
    assert "PostgreSQL admin connection failed" in capsys.readouterr().err
    assert not (tmp_path / "out.sql").exists()


def _admin_engine_for(database_url: str) -> sa.Engine:
    return sa.create_engine(
        make_url(database_url).set(drivername="postgresql+psycopg"),
        isolation_level="AUTOCOMMIT",
    )


@pytest.mark.skipif(not _LIVE_DATABASE, reason="Set RUN_INTEGRATION_TESTS=1 to run")
def test_live_render_captures_the_aud180_ddl_with_its_timeouts(
    tmp_path: Path,
) -> None:
    sql = renderer.render_revision_sql(_AUD180_MIGRATION, os.environ["DATABASE_URL"])

    assert sql.startswith(
        "-- observed SQLAlchemy begin event; transaction-event representation, "
        "not cursor text\nBEGIN;\n"
    )
    lock_timeout_position = sql.index("SET LOCAL lock_timeout = '10s'")
    statement_timeout_position = sql.index("SET LOCAL statement_timeout = '60s'")
    first_ddl_position = sql.index("CREATE TABLE news_media_assets (")
    assert lock_timeout_position < statement_timeout_position < first_ddl_position
    assert "CREATE TABLE news_media_assets (" in sql
    assert (
        "CREATE INDEX ix_news_media_assets_owner_user_id "
        "ON news_media_assets (owner_user_id);"
    ) in sql


@pytest.mark.skipif(not _LIVE_DATABASE, reason="Set RUN_INTEGRATION_TESTS=1 to run")
def test_live_render_captures_inspector_guarded_branches_hidden_offline(
    tmp_path: Path,
) -> None:
    # The offline inspector reports no constraints, so the restore branch that
    # adds the shadow CHECK constraint is absent from offline --sql output.
    sql = renderer.render_revision_sql(_GUARDED_MIGRATION, os.environ["DATABASE_URL"])

    assert "ADD CONSTRAINT ck_groups_id_shadow_not_null" in sql
    assert "CREATE TEMP TABLE _groups_fk_restore" in sql


@pytest.mark.skipif(not _LIVE_DATABASE, reason="Set RUN_INTEGRATION_TESTS=1 to run")
def test_live_render_of_the_root_revision_needs_no_parent_upgrade() -> None:
    sql = renderer.render_revision_sql(_ROOT_MIGRATION, os.environ["DATABASE_URL"])

    assert "CREATE TABLE" in sql


@pytest.mark.skipif(not _LIVE_DATABASE, reason="Set RUN_INTEGRATION_TESTS=1 to run")
def test_live_render_drops_its_scratch_database_and_restores_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.environ["DATABASE_URL"]
    fixed = uuid.UUID(hex="0123456789abcdef0123456789abcdef")
    monkeypatch.setattr(renderer, "uuid", SimpleNamespace(uuid4=lambda: fixed))
    scratch = f"alembic_squawk_{fixed.hex[:16]}"

    renderer.render_revision_sql(_AUD180_MIGRATION, database_url)

    admin = _admin_engine_for(database_url)
    try:
        with admin.connect() as connection:
            remaining = connection.scalar(
                sa.text("SELECT count(*) FROM pg_database WHERE datname = :name"),
                {"name": scratch},
            )
    finally:
        admin.dispose()
    assert remaining == 0
    assert os.environ["DATABASE_URL"] == database_url


@pytest.mark.skipif(not _LIVE_DATABASE, reason="Set RUN_INTEGRATION_TESTS=1 to run")
def test_live_render_restores_an_unset_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.environ["DATABASE_URL"]
    monkeypatch.delenv("DATABASE_URL")

    sql = renderer.render_revision_sql(_AUD180_MIGRATION, database_url)

    assert "CREATE TABLE news_media_assets (" in sql
    assert "DATABASE_URL" not in os.environ


def test_script_entry_point_exits_with_the_usage_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["render_live_alembic_sql.py"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(
            str(_PROJECT_ROOT / "scripts" / "quality" / "render_live_alembic_sql.py"),
            run_name="__main__",
        )

    assert exit_info.value.code == 2


@pytest.mark.skipif(not _LIVE_DATABASE, reason="Set RUN_INTEGRATION_TESTS=1 to run")
def test_main_writes_the_rendered_sql_to_the_output_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", os.environ["DATABASE_URL"])
    output = tmp_path / "aud180.sql"

    assert renderer.main([str(_AUD180_MIGRATION), str(output)]) == 0
    assert "CREATE TABLE news_media_assets (" in output.read_text(encoding="utf-8")
