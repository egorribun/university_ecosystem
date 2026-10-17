"""Regression coverage for Alembic revision metadata and SQL contracts."""

import io
import os
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

from scripts.quality.read_alembic_revision import (
    RevisionMetadataError,
    read_revision_metadata,
)


def _write_migration(tmp_path: Path, source: str) -> Path:
    migration = tmp_path / "migration.py"
    migration.write_text(source, encoding="utf-8")
    return migration


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            'revision: str = "annotated"\ndown_revision: str | None = "parent"\n',
            ("annotated", "parent"),
        ),
        (
            'revision = "plain"\ndown_revision = None\n',
            ("plain", "base"),
        ),
    ],
)
def test_reads_literal_plain_and_annotated_metadata(
    tmp_path: Path,
    source: str,
    expected: tuple[str, str],
) -> None:
    assert read_revision_metadata(_write_migration(tmp_path, source)) == expected


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("down_revision = None\n", "revision must be assigned exactly once"),
        ('revision = "only"\n', "down_revision must be assigned exactly once"),
        (
            'revision = "first"\nrevision: str = "second"\ndown_revision = None\n',
            "revision must be assigned exactly once",
        ),
        (
            "revision = make_revision()\ndown_revision = None\n",
            "revision must be a string literal",
        ),
        (
            "revision = 123\ndown_revision = None\n",
            "revision must be a string literal",
        ),
        (
            'revision = "child"\ndown_revision = ("left", "right")\n',
            "down_revision must be a string literal or None",
        ),
        (
            'revision = alias = "child"\ndown_revision = None\n',
            "revision must use a single-name assignment",
        ),
        (
            'if enabled:\n    revision = "conditional"\ndown_revision = None\n',
            "revision must be a top-level assignment",
        ),
        (
            'revision = ""\ndown_revision = None\n',
            "revision must not be empty",
        ),
    ],
)
def test_rejects_missing_dynamic_non_string_or_ambiguous_metadata(
    tmp_path: Path,
    source: str,
    message: str,
) -> None:
    with pytest.raises(RevisionMetadataError, match=message):
        read_revision_metadata(_write_migration(tmp_path, source))


def test_rejects_invalid_python(tmp_path: Path) -> None:
    migration = _write_migration(tmp_path, 'revision = "broken"\nif\n')

    with pytest.raises(RevisionMetadataError, match="invalid Python syntax"):
        read_revision_metadata(migration)


def test_ci_uses_the_fail_closed_revision_metadata_parser() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert (
        'uv run python scripts/quality/read_alembic_revision.py "$migration"'
        in workflow
    )
    assert 're.search(r"^revision' not in workflow


def test_alembic_history_does_not_require_runtime_secrets() -> None:
    """Revision discovery must work before application configuration exists."""

    environment = os.environ.copy()
    environment["ENV_FILE_PATH"] = ""
    for name in (
        "DATABASE_URL",
        "SECRET_KEY",
        "ENVIRONMENT",
        "APP_PROCESS_ROLE",
        "REVOCATION_REDIS_URL",
        "CACHE_REDIS_URL",
    ):
        environment.pop(name, None)

    result = subprocess.run(  # noqa: S603 - fixed local Alembic module invocation
        [sys.executable, "-m", "alembic", "history", "--verbose"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "202503150001" in result.stdout


_AUD180_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "202610120002_add_news_media_asset_ownership.py"
)


def _load_aud180_migration() -> dict[str, Any]:
    return runpy.run_path(str(_AUD180_MIGRATION))


def test_aud180_squawk_capture_emits_the_shared_ddl_in_a_transaction() -> None:
    migration = _load_aud180_migration()
    output = io.StringIO()
    migration_context = MigrationContext.configure(
        dialect=postgresql.dialect(),
        opts={
            "as_sql": True,
            "output_buffer": output,
            "transactional_ddl": True,
        },
    )

    with Operations.context(migration_context) as operations:
        with migration_context.begin_transaction():
            migration["_emit_news_media_asset_ddl"](operations)

    statements = [
        " ".join(statement.split())
        for statement in output.getvalue().split(";")
        if statement.strip()
    ]
    assert statements[:3] == [
        "BEGIN",
        "SET LOCAL lock_timeout = '10s'",
        "SET LOCAL statement_timeout = '60s'",
    ]
    assert len(statements) == 6
    table_ddl = statements[3]
    prefix = "CREATE TABLE news_media_assets ("
    assert table_ddl.startswith(prefix)
    table_parts = [
        part.strip()
        for part in table_ddl.removeprefix(prefix).removesuffix(")").split(", ")
    ]
    assert len(table_parts) == 10
    expected_parts = {
        "id UUID NOT NULL",
        "storage_url VARCHAR(2048) NOT NULL",
        "owner_user_id UUID",
        "news_id UUID",
        "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL",
        "PRIMARY KEY (id)",
        "CONSTRAINT uq_news_media_asset_storage_url UNIQUE (storage_url)",
        "CONSTRAINT uq_news_media_asset_news_id UNIQUE (news_id)",
    }
    assert expected_parts.issubset(table_parts)
    foreign_keys = {
        part.removeprefix("FOREIGN KEY(").removeprefix("FOREIGN KEY (")
        for part in table_parts
        if part.startswith("FOREIGN KEY")
    }
    assert foreign_keys == {
        "owner_user_id) REFERENCES users (id) ON DELETE SET NULL",
        "news_id) REFERENCES news (id) ON DELETE SET NULL",
    }
    assert statements[4] == (
        "CREATE INDEX ix_news_media_assets_owner_user_id "
        "ON news_media_assets (owner_user_id)"
    )
    assert statements[5] == "COMMIT"


def test_aud180_upgrade_still_rejects_offline_execution() -> None:
    migration = _load_aud180_migration()
    migration_context = MigrationContext.configure(
        dialect=postgresql.dialect(),
        opts={"as_sql": True, "output_buffer": io.StringIO()},
    )

    with Operations.context(migration_context):
        with pytest.raises(RuntimeError, match="requires online PostgreSQL"):
            migration["upgrade"]()


def test_aud180_squawk_workflow_uses_capture_only_for_its_revision() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert 'if [ "$revision" = "202610120002" ]; then' in workflow
    assert "migration._emit_news_media_asset_ddl(operations)" in workflow
    assert "with migration_context.begin_transaction():" in workflow
    assert 'uv run alembic upgrade "$down_revision:$revision" --sql' in workflow
    assert 'squawk "${squawk_args[@]}"' in workflow
