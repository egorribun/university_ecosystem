"""Exercise a reversible migration roundtrip and the declared downgrade boundary."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path, PurePosixPath
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet
from testcontainers.community.postgres import PostgresContainer

from alembic import command
from scripts.quality import migration_downgrade_policy
from tests.integration.owned_postgres import _LoopbackMigrationPostgres
from tests.test_helm_staging_contract import _render_staging

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]


@pytest.fixture(scope="module")
def migration_postgres():
    """Provides isolated PostgreSQL, reusing the bounded operator when requested."""
    operator_url = os.environ.get("MIGRATION_ROUNDTRIP_DATABASE_URL")
    if operator_url:
        yield _LoopbackMigrationPostgres(operator_url)
        return

    with PostgresContainer(
        "pgvector/pgvector:pg17@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d"
    ) as postgres:
        yield postgres


def test_migration_supported_roundtrip_and_irreversible_boundary(
    migration_postgres,
) -> None:
    """Round-trip a reversible migration and verify the PostgreSQL boundary."""
    url_sync = migration_postgres.get_connection_url(driver="psycopg")
    url_asyncpg = migration_postgres.get_connection_url(driver="asyncpg")

    orig_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url_asyncpg

    try:
        # Initialize Alembic Config pointing to the isolated testcontainer.
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
        config.set_main_option("sqlalchemy.url", url_asyncpg)
        plan = migration_downgrade_policy.build_downgrade_plan(
            PROJECT_ROOT / "alembic" / "versions"
        )
        assert plan.boundary_revision is not None
        assert plan.boundary_parent is not None
        assert plan.safe_target == plan.boundary_revision

        # Round-trip the schema-changing groups demo-key revision. It is before
        # the latest boundary and its parent, so this never crosses a barrier.
        command.upgrade(config, "202609300002")
        command.downgrade(config, "202609300001")
        command.upgrade(config, "202609300002")

        # Follow the policy's safe path through the boundary to the current head.
        command.upgrade(config, plan.boundary_parent)
        command.upgrade(config, "head")
        command.downgrade(config, plan.safe_target)
        command.upgrade(config, "head")
        inspection_engine = sa.create_engine(url_sync)
        sentinel_id = uuid4()
        sentinel_url = f"https://example.invalid/migration-roundtrip/{sentinel_id}"
        try:
            # Commit a marker before the probe so transaction rollback must retain it.
            with inspection_engine.begin() as connection:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO news_media_assets (id, storage_url)
                        VALUES (:id, :storage_url)
                        """
                    ).bindparams(sa.bindparam("id", type_=sa.Uuid())),
                    {"id": sentinel_id, "storage_url": sentinel_url},
                )

            boundary_connection = inspection_engine.connect()
            boundary_transaction = None
            try:
                boundary_transaction = boundary_connection.begin()
                config.attributes["connection"] = boundary_connection
                try:
                    migration_downgrade_policy.assert_declared_boundary(
                        plan, lambda target: command.downgrade(config, target)
                    )

                    # 002 is a no-op downgrade, but Alembic still stamps 001 before
                    # the irreversible 001 downgrade raises. Prove that this partial
                    # stamp and the protected data/schema are visible inside the
                    # outer transaction before rolling the diagnostic back.
                    assert (
                        MigrationContext.configure(
                            boundary_connection
                        ).get_current_revision()
                        == plan.safe_target
                    )
                    assert (
                        boundary_connection.execute(
                            sa.text(
                                "SELECT storage_url FROM news_media_assets WHERE id = :id"
                            ).bindparams(sa.bindparam("id", type_=sa.Uuid())),
                            {"id": sentinel_id},
                        ).scalar_one()
                        == sentinel_url
                    )
                    dnd_types = boundary_connection.execute(
                        sa.text(
                            """
                            SELECT column_name, data_type
                              FROM information_schema.columns
                             WHERE table_schema = current_schema()
                               AND table_name = 'user_preferences'
                               AND column_name IN ('dnd_start', 'dnd_end')
                            """
                        )
                    ).mappings()
                    assert {
                        row["column_name"]: row["data_type"] for row in dnd_types
                    } == {
                        "dnd_start": "time without time zone",
                        "dnd_end": "time without time zone",
                    }
                finally:
                    config.attributes.pop("connection", None)
                    if boundary_transaction.is_active:
                        boundary_transaction.rollback()
            finally:
                boundary_connection.close()

            # The head revision, data marker, and irreversible schema
            # survive the failed probe after its external transaction is rolled back.
            with inspection_engine.connect() as connection:
                assert (
                    MigrationContext.configure(connection).get_current_revision()
                    == plan.head_revision
                )
                assert (
                    connection.execute(
                        sa.text(
                            "SELECT storage_url FROM news_media_assets WHERE id = :id"
                        ).bindparams(sa.bindparam("id", type_=sa.Uuid())),
                        {"id": sentinel_id},
                    ).scalar_one()
                    == sentinel_url
                )
                dnd_types = connection.execute(
                    sa.text(
                        """
                        SELECT column_name, data_type
                          FROM information_schema.columns
                         WHERE table_schema = current_schema()
                           AND table_name = 'user_preferences'
                           AND column_name IN ('dnd_start', 'dnd_end')
                        """
                    )
                ).mappings()
                assert {row["column_name"]: row["data_type"] for row in dnd_types} == {
                    "dnd_start": "time without time zone",
                    "dnd_end": "time without time zone",
                }
        finally:
            config.attributes.pop("connection", None)
            inspection_engine.dispose()

    finally:
        if orig_db_url is not None:
            os.environ["DATABASE_URL"] = orig_db_url
        else:
            del os.environ["DATABASE_URL"]


def _migration_cli_base_environment() -> dict[str, str]:
    """Build a clean child environment so host CI or .env values cannot mask files."""
    inherited_names = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR")
    environment = {
        name: os.environ[name] for name in inherited_names if name in os.environ
    }
    environment.update(
        {
            "ENV_FILE_PATH": "",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": str(PROJECT_ROOT),
            "PYTHONUTF8": "1",
        }
    )
    return environment


def _rendered_migration_environment() -> dict[str, str]:
    release = "aud168-online-runtime-contract"
    resources = _render_staging(release_name=release)
    job = next(
        resource
        for resource in resources
        if resource.get("kind") == "Job"
        and resource.get("metadata", {}).get("name", "").endswith("-migrate")
    )
    container = next(
        item
        for item in job["spec"]["template"]["spec"]["containers"]
        if item["name"] == "migrate"
    )
    result = {
        item["name"]: str(item["value"]) for item in container["env"] if "value" in item
    }
    assert result["ENVIRONMENT"] == "staging"
    assert result["APP_PROCESS_ROLE"] == "api"
    assert "DATABASE_URL" not in result
    assert "SECRET_KEY" not in result
    assert "DATABASE_URL_FILE" in result
    assert "SECRET_KEY_FILE" in result
    assert "CI" not in result
    assert "GITHUB_ACTIONS" not in result
    return result


def _write_rendered_secret_files(
    rendered_environment: dict[str, str],
    root: Path,
    database_url: str,
) -> tuple[dict[str, str], tuple[str, ...]]:
    environment = _migration_cli_base_environment()
    environment.update(
        {
            name: value
            for name, value in rendered_environment.items()
            if not name.endswith("_FILE")
        }
    )
    secret_values: list[str] = []
    for variable, mount_path in rendered_environment.items():
        if not variable.endswith("_FILE"):
            continue
        mount_parts = PurePosixPath(mount_path).parts
        assert mount_parts[:3] == ("/", "run", "secrets")
        assert len(mount_parts) == 5
        secret_path = root.joinpath(*mount_parts[-2:])
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        if variable == "DATABASE_URL_FILE":
            contents = database_url
        elif variable == "CACHE_REDIS_URL_FILE":
            contents = "redis://cache-fixture.invalid:6379/0"
        elif variable == "REVOCATION_REDIS_URL_FILE":
            contents = "redis://revocation-fixture.invalid:6379/0"
        elif variable == "MFA_TOTP_ENCRYPTION_KEYS_FILE":
            active_key_id = environment["MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID"]
            encryption_key = Fernet.generate_key().decode("ascii")
            contents = f"{active_key_id}:{encryption_key}"
            secret_values.append(encryption_key)
        elif variable == "SPOTIFY_TOKEN_SECRET_FILE":
            contents = Fernet.generate_key().decode("ascii")
        else:
            # Generated only for this isolated settings/migration process.
            contents = uuid4().hex + uuid4().hex
        secret_path.write_text(contents, encoding="utf-8")
        secret_values.append(contents)
        environment[variable] = str(secret_path)
    return environment, tuple(secret_values)


def _run_online_upgrade(
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - current interpreter and fixed local Alembic argv; no shell
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(PROJECT_ROOT / "alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )


def _safe_process_diagnostic(
    result: subprocess.CompletedProcess[str], secret_values: tuple[str, ...]
) -> str:
    diagnostic = f"{result.stdout}\n{result.stderr}"
    for secret_value in secret_values:
        if secret_value:
            diagnostic = diagnostic.replace(secret_value, "[redacted]")
    return diagnostic[-4000:]


def test_staging_online_alembic_uses_rendered_file_secrets_and_advances_head(
    migration_postgres, tmp_path: Path
) -> None:
    """A rendered staging role must not silently return on fallback settings."""
    base_url = sa.engine.make_url(
        migration_postgres.get_connection_url(driver="psycopg")
    )
    database_name = f"test_{uuid4().hex[:20]}"
    assert len(database_name) == 25
    assert all(character in "0123456789abcdef" for character in database_name[5:])
    admin_url = base_url.set(drivername="postgresql+psycopg", database="postgres")
    target_async_url = base_url.set(
        drivername="postgresql+asyncpg", database=database_name
    ).render_as_string(hide_password=False)
    target_sync_url = base_url.set(
        drivername="postgresql+psycopg", database=database_name
    )
    admin_engine = sa.create_engine(
        admin_url, isolation_level="AUTOCOMMIT", hide_parameters=True
    )
    database_created = False
    inspection_engine: sa.Engine | None = None
    try:
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        database_created = True
        inspection_engine = sa.create_engine(target_sync_url, hide_parameters=True)
        rendered_environment = _rendered_migration_environment()
        staging_environment, secret_values = _write_rendered_secret_files(
            rendered_environment,
            tmp_path / "mounted-secrets",
            target_async_url,
        )

        # A configured but missing key must fail closed before Alembic creates
        # its version table; it may not generate a development signing key.
        invalid_environment = dict(staging_environment)
        missing_key_path = tmp_path / "missing-application-key"
        invalid_environment["SECRET_KEY_FILE"] = str(missing_key_path)
        invalid = _run_online_upgrade(invalid_environment)
        assert invalid.returncode != 0
        with inspection_engine.connect() as connection:
            assert (
                connection.scalar(
                    sa.text("SELECT to_regclass('public.alembic_version')")
                )
                is None
            )

        # The documented local fallback remains available only in explicit
        # development mode and skips before opening even its fallback SQLite URL.
        development_environment = _migration_cli_base_environment()
        development_environment["ENVIRONMENT"] = "development"
        development = _run_online_upgrade(development_environment)
        assert development.returncode == 0
        assert "Skipping Alembic migrations: has_development_fallbacks is True." in (
            development.stdout + development.stderr
        )
        with inspection_engine.connect() as connection:
            assert (
                connection.scalar(
                    sa.text("SELECT to_regclass('public.alembic_version')")
                )
                is None
            )

        completed = _run_online_upgrade(staging_environment)
        assert completed.returncode == 0, _safe_process_diagnostic(
            completed, secret_values
        )
        alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
        alembic_config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
        expected_heads = set(ScriptDirectory.from_config(alembic_config).get_heads())
        with inspection_engine.connect() as connection:
            applied_heads = set(
                connection.scalars(sa.text("SELECT version_num FROM alembic_version"))
            )
        assert applied_heads == expected_heads
    finally:
        if inspection_engine is not None:
            inspection_engine.dispose()
        if database_created:
            with admin_engine.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE "{database_name}"')
        admin_engine.dispose()
