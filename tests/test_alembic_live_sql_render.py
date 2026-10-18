"""Live PostgreSQL rendering of changed Alembic revisions for Squawk (AUD-208)."""

from __future__ import annotations

import os
import runpy
import sys
import uuid
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

    assert sql.startswith("SET LOCAL lock_timeout = '10s';\n")
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
