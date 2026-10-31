"""Regression coverage for Alembic revision metadata and SQL contracts."""

import io
import os
import re
import runpy
import secrets
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.fernet import Fernet
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


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Loopback port 9 is never served, so a migration that reaches the connection
# step fails closed instead of touching a real database.
_UNREACHABLE_DATABASE_URL = (
    "postgresql+asyncpg://migration-gate@127.0.0.1:9/unreachable"
)


def _alembic_cli_environment(**overrides: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment["ENV_FILE_PATH"] = ""
    for name in (
        "DATABASE_URL",
        "SECRET_KEY",
        "ENVIRONMENT",
        "APP_PROCESS_ROLE",
        "REVOCATION_REDIS_URL",
        "CACHE_REDIS_URL",
        "CI",
        "GITHUB_ACTIONS",
    ):
        environment.pop(name, None)
    environment.update(overrides)
    return environment


def _run_alembic_cli(
    arguments: list[str],
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed local Alembic module invocation
        [sys.executable, "-m", "alembic", *arguments],
        cwd=_PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_alembic_history_does_not_require_runtime_secrets() -> None:
    """Revision discovery must work before application configuration exists."""

    result = _run_alembic_cli(["history", "--verbose"], _alembic_cli_environment())

    assert result.returncode == 0, result.stderr
    assert "202503150001" in result.stdout


def _staging_environment_without_secret_key() -> dict[str, str]:
    """Every staging-required value except SECRET_KEY, generated at runtime."""

    values = {
        name: secrets.token_hex(32)
        for name in (
            "AUDIT_LOG_SECRET",
            "ELASTICSEARCH_PASSWORD",
            "INTERNAL_AUTH_TOKEN",
            "INTERNAL_HMAC_SECRET",
            "NATS_AUTH_TOKEN",
            "SPICEDB_PRESHARED_KEY",
            "TOKEN_HMAC_SECRET",
            "WS_HUB_INTERNAL_SECRET",
        )
    }
    # conftest.py sets ALGORITHM=HS256 for the pytest process; staging must use
    # the production signing algorithm, so the subprocess states it explicitly.
    values.update(
        ALGORITHM="RS256",
        APP_PROCESS_ROLE="api",
        # AUD-164: the staging API role must name its gateway peers. Migrations run
        # as that role (charts/.../migration-job.yaml), so the fixture supplies it.
        TRUSTED_PROXIES="10.0.0.0/8",
        AUTO_CREATE_SCHEMA="false",
        CACHE_REDIS_URL="redis://cache.staging.internal:6379/0",
        RATE_LIMIT_STORAGE_BACKEND="redis",
        RATE_LIMIT_STORAGE_URI="redis://localhost",
        ELASTICSEARCH_URL="https://elasticsearch.staging.internal",
        EVENT_FILE_SCANNER_ENABLED="true",
        MINIO_SECURE="true",
        MFA_TOTP_ENCRYPTION_KEYS=f"test-key:{Fernet.generate_key().decode('ascii')}",
        MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID="test-key",
        SPOTIFY_TOKEN_SECRET=Fernet.generate_key().decode("ascii"),
        REVOCATION_REDIS_ACCESS_ENABLED="true",
        REVOCATION_REDIS_URL="redis://revocation.staging.internal:6379/0",
    )
    return values


def test_alembic_upgrade_fails_closed_when_ci_allows_fallback_outside_development() -> (
    None
):
    """AUD-168: CI must not turn a non-development SECRET_KEY fallback into exit 0."""

    result = _run_alembic_cli(
        ["upgrade", "head"],
        _alembic_cli_environment(
            **_staging_environment_without_secret_key(),
            ENVIRONMENT="staging",
            CI="true",
            DATABASE_URL=_UNREACHABLE_DATABASE_URL,
        ),
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert "Refusing to skip Alembic migrations" in output
    assert "Skipping Alembic migrations" not in output


def test_alembic_upgrade_never_skips_an_explicit_database_in_development() -> None:
    """AUD-168: an explicit DATABASE_URL is a request to migrate that database."""

    result = _run_alembic_cli(
        ["upgrade", "head"],
        _alembic_cli_environment(
            ENVIRONMENT="development",
            DATABASE_URL=_UNREACHABLE_DATABASE_URL,
        ),
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert "Refusing to skip Alembic migrations" in output
    assert "Skipping Alembic migrations" not in output


_MIGRATION_COMMAND = re.compile(r"\balembic\b[^\n]*\b(?:upgrade|downgrade|check)\b")


def _workflow_migration_violations() -> list[str]:
    violations: list[str] = []
    for path in sorted((_PROJECT_ROOT / ".github" / "workflows").glob("*.yml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        workflow_env = workflow.get("env") or {}
        for job_name, job in (workflow.get("jobs") or {}).items():
            job_env = {**workflow_env, **(job.get("env") or {})}
            secret_generated = False
            for step in job.get("steps") or []:
                run = step.get("run") or ""
                if "SECRET_KEY=" in run and "GITHUB_ENV" in run:
                    secret_generated = True
                if not _MIGRATION_COMMAND.search(run):
                    continue
                step_env = {**job_env, **(step.get("env") or {})}
                for required in ("DATABASE_URL", "ENVIRONMENT"):
                    if not step_env.get(required):
                        violations.append(f"{path.name}:{job_name} lacks {required}")
                if not step_env.get("SECRET_KEY") and not secret_generated:
                    violations.append(f"{path.name}:{job_name} lacks SECRET_KEY")
    return violations


def test_every_workflow_migration_step_supplies_settings_explicitly() -> None:
    """AUD-168: CI migration steps must not depend on a silently skipped fallback."""

    assert _workflow_migration_violations() == []


def test_alembic_upgrade_keeps_the_documented_development_skip() -> None:
    """The local SQLite default in development remains an explicit, warned skip."""

    result = _run_alembic_cli(
        ["upgrade", "head"],
        _alembic_cli_environment(ENVIRONMENT="development"),
    )
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert "Skipping Alembic migrations: has_development_fallbacks is True." in output


_AUD180_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "202610120002_add_news_media_asset_ownership.py"
)
_PARTITION_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "202607020001_create_range_partitions.py"
)
_SCHEMA_DRIFT_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "202607280001_reconcile_schema_drift.py"
)


def _load_aud180_migration() -> dict[str, Any]:
    return runpy.run_path(str(_AUD180_MIGRATION))


def test_partition_migration_sets_timeouts_before_catalog_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = runpy.run_path(str(_PARTITION_MIGRATION))

    class EmptyCatalogConnection:
        dialect = SimpleNamespace(name="postgresql")

        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement: Any, _parameters: Any = None) -> Any:
            self.statements.append(str(statement))
            return SimpleNamespace(fetchone=lambda: None)

    connection = EmptyCatalogConnection()
    monkeypatch.setattr(migration["op"], "get_bind", lambda: connection)

    migration["upgrade"]()

    assert connection.statements[:2] == [
        "SET LOCAL lock_timeout = '10s'",
        "SET LOCAL statement_timeout = '60s'",
    ]
    assert connection.statements[2].lstrip().startswith("SELECT c.relkind")


def test_schema_drift_migration_sets_timeouts_before_catalog_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = runpy.run_path(str(_SCHEMA_DRIFT_MIGRATION))
    statements: list[str] = []
    observed_bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    inspected: list[object] = []

    def inspect_after_timeouts(bind: object) -> SimpleNamespace:
        assert statements[:2] == [
            "SET LOCAL lock_timeout = '10s'",
            "SET LOCAL statement_timeout = '60s'",
        ]
        inspected.append(bind)
        return SimpleNamespace(
            get_table_names=lambda: ["tenants", "vector_chunks", "grades"]
        )

    monkeypatch.setattr(migration["op"], "get_bind", lambda: observed_bind)
    monkeypatch.setattr(
        migration["op"], "execute", lambda statement: statements.append(str(statement))
    )
    monkeypatch.setattr(migration["sa"], "inspect", inspect_after_timeouts)

    migration["upgrade"]()

    assert inspected == [observed_bind]
    assert statements[:2] == [
        "SET LOCAL lock_timeout = '10s'",
        "SET LOCAL statement_timeout = '60s'",
    ]
    assert statements[2:] == [
        "ALTER TABLE tenants DROP CONSTRAINT IF EXISTS tenants_slug_key CASCADE",
        "ALTER TABLE tenants DROP CONSTRAINT IF EXISTS tenants_domain_key CASCADE",
    ]


def test_schema_drift_migration_sets_timeouts_before_downgrade_drops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = runpy.run_path(str(_SCHEMA_DRIFT_MIGRATION))
    statements: list[str] = []

    monkeypatch.setattr(
        migration["op"], "execute", lambda statement: statements.append(str(statement))
    )

    migration["downgrade"]()

    assert statements[:2] == [
        "SET LOCAL lock_timeout = '10s'",
        "SET LOCAL statement_timeout = '60s'",
    ]
    assert statements[2:] == [
        "DROP TABLE IF EXISTS grades CASCADE",
        "DROP TABLE IF EXISTS vector_chunks CASCADE",
    ]


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


_SQUAWK_RULES_THAT_MUST_LINT = (
    "require-timeout-settings",
    "require-concurrent-index-creation",
    "require-concurrent-index-deletion",
    "adding-foreign-key-constraint",
    "constraint-missing-not-valid",
)


def _squawk_step(workflow: str) -> str:
    start = workflow.index("      - name: Lint Postgres Migrations (Squawk)")
    return workflow[start : workflow.index("      - name: Wait for PostgreSQL", start)]


def test_squawk_lints_live_rendered_sql_without_index_fk_or_timeout_exclusions() -> (
    None
):
    """AUD-208: changed revisions are linted from live PostgreSQL DDL, not --sql stubs."""

    step = _squawk_step(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))

    assert "python -m scripts.quality.render_live_alembic_sql" in step
    assert "alembic upgrade" not in step
    assert "_emit_news_media_asset_ddl" not in step
    for rule in _SQUAWK_RULES_THAT_MUST_LINT:
        assert f"--exclude {rule}" not in step
    assert '"$squawk_binary_path" "${squawk_args[@]}" "$sql_file"' in step
