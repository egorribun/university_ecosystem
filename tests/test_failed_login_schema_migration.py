"""Contracts for the failed-login schema reconciliation migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "alembic" / "versions" / "202608270002_reconcile_failed_login_schema.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("failed_login_reconcile", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_is_attached_to_current_alembic_head() -> None:
    migration = _load_migration()

    assert migration.revision == "202608270002"
    assert migration.down_revision == "202608270001"


def test_reconciliation_restores_every_model_index_and_set_null_fk() -> None:
    migration = _load_migration()
    names = {name for name, _columns in migration._INDEXES}

    assert names == {
        "ix_failed_login_attempts_attempted_at",
        "ix_failed_login_attempts_email",
        "ix_failed_login_attempts_email_attempted_at",
        "ix_failed_login_attempts_ip_address",
        "ix_failed_login_attempts_ip_attempted_at",
        "ix_failed_login_attempts_user_id",
    }
    assert migration._FK_NAME == "fk_failed_login_attempts_user_id"
    assert migration._foreign_key_matches(
        {
            "constrained_columns": ["user_id"],
            "referred_table": "users",
            "referred_columns": ["id"],
            "options": {"ondelete": "SET NULL"},
        }
    )
    assert not migration._foreign_key_matches(
        {
            "constrained_columns": ["user_id"],
            "referred_table": "users",
            "referred_columns": ["id"],
            "options": {"ondelete": "CASCADE"},
        }
    )
    assert migration._index_matches(
        {"column_names": ["email", "attempted_at"], "unique": False},
        ("email", "attempted_at"),
    )
    assert not migration._index_matches(
        {"column_names": ["email"], "unique": False},
        ("email", "attempted_at"),
    )
    assert not migration._index_matches(
        {"column_names": ["email", "attempted_at"], "unique": True},
        ("email", "attempted_at"),
    )


def test_sqlite_upgrade_replaces_unnamed_wrong_fk_without_losing_rows() -> None:
    """Batch mode must remove an unnamed legacy CASCADE relation safely."""

    migration = _load_migration()
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.exec_driver_sql(
                "CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE failed_login_attempts (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36),
                    email VARCHAR(254) NOT NULL,
                    ip_address VARCHAR(45),
                    user_agent VARCHAR(512),
                    attempted_at DATETIME,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            connection.exec_driver_sql("INSERT INTO users VALUES ('u1')")
            connection.exec_driver_sql(
                "INSERT INTO failed_login_attempts VALUES ('a1', 'u1', 'x@example.test', NULL, NULL, CURRENT_TIMESTAMP)"
            )

            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()
                migration.upgrade()

            fk = connection.exec_driver_sql(
                "PRAGMA foreign_key_list(failed_login_attempts)"
            ).fetchall()
            rows = connection.exec_driver_sql(
                "SELECT id, user_id FROM failed_login_attempts"
            ).fetchall()

            assert len(fk) == 1
            assert fk[0][6].upper() == "SET NULL"
            assert rows == [("a1", "u1")]
    finally:
        engine.dispose()


def test_upgrade_fails_closed_on_same_name_wrong_index_definition() -> None:
    migration = _load_migration()
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE failed_login_attempts (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36),
                    email VARCHAR(254) NOT NULL,
                    ip_address VARCHAR(45),
                    user_agent VARCHAR(512),
                    attempted_at DATETIME
                )
                """
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_failed_login_attempts_attempted_at ON failed_login_attempts (email)"
            )

            context = MigrationContext.configure(connection)
            with (
                Operations.context(context),
                pytest.raises(RuntimeError, match="does not match"),
            ):
                migration.upgrade()
    finally:
        engine.dispose()


def test_downgrade_is_non_destructive_without_object_ownership_provenance() -> None:
    migration = _load_migration()
    source = MIGRATION.read_text(encoding="utf-8")

    assert "def downgrade()" in source
    assert "op.drop_index" not in source
    assert "drop_constraint" not in source.split("def downgrade", 1)[1]
    assert migration.downgrade is not None
