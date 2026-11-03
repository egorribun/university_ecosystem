"""Regression coverage for Alembic revision metadata and SQL contracts."""

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from scripts.quality.read_alembic_revision import (
    RevisionMetadataError,
    read_revision_metadata,
)
from tests.fixtures.baseline_migration import (
    BASELINE_PATH,
    assert_downgrade_refuses,
    assert_exact_statements,
    bind_baseline,
    capture_baseline,
    table_statements,
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
# This URL is observed at the engine factory; no engine or connection is created.
_EXPLICIT_DATABASE_URL = "postgresql+asyncpg://migration-gate@migration.invalid/target"
_TARGET_PROBE = textwrap.dedent(
    """
    import json
    import runpy
    import sys

    import sqlalchemy
    import sqlalchemy.ext.asyncio

    class ExplicitTargetObserved(RuntimeError):
        pass

    def observe_target(options, *, prefix, poolclass):
        print("ALEMBIC_TARGET=" + json.dumps({
            "url": options["sqlalchemy.url"],
            "prefix": prefix,
            "null_pool": poolclass is sqlalchemy.pool.NullPool,
        }), flush=True)
        raise ExplicitTargetObserved("stopped before engine creation")

    sqlalchemy.engine_from_config = observe_target
    sqlalchemy.ext.asyncio.async_engine_from_config = observe_target
    sys.argv = ["alembic", "upgrade", "head"]
    runpy.run_module("alembic", run_name="__main__")
    """
)


def _alembic_cli_environment(**overrides: str) -> dict[str, str]:
    controlled_names = (
        "DATABASE_URL",
        "DATABASE_URL_FILE",
        "SECRET_KEY",
        "SECRET_KEY_FILE",
        "ENVIRONMENT",
        "APP_PROCESS_ROLE",
        "REVOCATION_REDIS_URL",
        "CACHE_REDIS_URL",
        "CI",
        "GITHUB_ACTIONS",
    )
    controlled = {name.casefold() for name in controlled_names}
    environment = {
        name: value
        for name, value in os.environ.items()
        if name.casefold() not in controlled and not name.casefold().endswith("_file")
    }
    environment["ENV_FILE_PATH"] = ""
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
    assert "Rev: 202611020000 (head)\nParent: <base>\n" in result.stdout
    assert result.stdout.count("Rev: ") == 1


@pytest.mark.parametrize("environment_name", ["staging", "development"])
def test_alembic_upgrade_uses_explicit_target_without_runtime_secrets(
    environment_name: str,
) -> None:
    """Observe the explicit target without creating an engine or using the network."""

    result = subprocess.run(  # noqa: S603 - fixed local no-network Alembic probe
        [sys.executable, "-c", _TARGET_PROBE],
        cwd=_PROJECT_ROOT,
        env=_alembic_cli_environment(
            ENVIRONMENT=environment_name,
            CI="true",
            DATABASE_URL=_EXPLICIT_DATABASE_URL,
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=120,
    )
    output = result.stdout + result.stderr
    target_lines = [
        line.removeprefix("ALEMBIC_TARGET=")
        for line in result.stdout.splitlines()
        if line.startswith("ALEMBIC_TARGET=")
    ]

    assert result.returncode != 0, output
    assert len(target_lines) == 1, output
    assert json.loads(target_lines[0]) == {
        "url": _EXPLICIT_DATABASE_URL,
        "prefix": "sqlalchemy.",
        "null_pool": True,
    }
    assert "ExplicitTargetObserved: stopped before engine creation" in result.stderr
    assert "Skipping Alembic migrations" not in output
    assert "Missing required environment variables" not in output


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


def test_alembic_upgrade_refuses_the_implicit_development_target() -> None:
    """A development metadata default is never an explicit migration target."""

    result = _run_alembic_cli(
        ["upgrade", "head"],
        _alembic_cli_environment(ENVIRONMENT="development"),
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert "Database URL is not configured for Alembic" in output
    assert "Skipping Alembic migrations" not in output


def test_baseline_revision_metadata_is_a_fresh_root() -> None:
    assert read_revision_metadata(BASELINE_PATH) == ("202611020000", "base")
    assert sorted(BASELINE_PATH.parent.glob("*.py")) == [BASELINE_PATH]


def test_baseline_sets_timeouts_before_catalog_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = bind_baseline(monkeypatch)
    execute = operations.bind.execute

    def inspect_after_timeouts(statement: object) -> object:
        assert operations.statements[:2] == [
            "SET LOCAL lock_timeout = '10s'",
            "SET LOCAL statement_timeout = '60s'",
        ]
        return execute(statement)

    monkeypatch.setattr(operations.bind, "execute", inspect_after_timeouts)
    migration.upgrade()
    assert len(operations.bind.reads) == 1


def test_baseline_downgrade_refuses_before_catalog_access_or_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = bind_baseline(monkeypatch)
    assert_downgrade_refuses(migration, operations)


def _assert_news_media_asset_ddl(statements: list[str]) -> None:
    assert_exact_statements(
        table_statements(statements, "news_media_assets"),
        (
            "CREATE TABLE public.news_media_assets (\n"
            "    id uuid NOT NULL,\n"
            "    storage_url character varying(2048) NOT NULL,\n"
            "    owner_user_id uuid,\n"
            "    news_id uuid,\n"
            "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
            "    CONSTRAINT news_media_assets_pkey PRIMARY KEY (id)\n"
            ")",
            "ALTER TABLE ONLY public.news_media_assets\n"
            "    ADD CONSTRAINT uq_news_media_asset_news_id UNIQUE (news_id)",
            "ALTER TABLE ONLY public.news_media_assets\n"
            "    ADD CONSTRAINT uq_news_media_asset_storage_url UNIQUE (storage_url)",
            "ALTER TABLE ONLY public.news_media_assets\n"
            "    ADD CONSTRAINT news_media_assets_news_id_fkey FOREIGN KEY (news_id) "
            "REFERENCES public.news(id) ON DELETE SET NULL",
            "ALTER TABLE ONLY public.news_media_assets\n"
            "    ADD CONSTRAINT news_media_assets_owner_user_id_fkey FOREIGN KEY "
            "(owner_user_id) REFERENCES public.users(id) ON DELETE SET NULL",
            "CREATE INDEX ix_news_media_assets_owner_user_id ON public.news_media_assets "
            "USING btree (owner_user_id)",
        ),
    )


def test_baseline_preserves_aud180_news_media_asset_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_news_media_asset_ddl(operations.statements)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("news_media_assets_pkey", "news_media_assets_wrong_pkey"),
        ("PRIMARY KEY (id)", "PRIMARY KEY (news_id)"),
        (",\n    CONSTRAINT news_media_assets_pkey PRIMARY KEY (id)", ""),
        ("character varying(2048)", "character varying(1024)"),
        ("UNIQUE (news_id)", "UNIQUE (owner_user_id)"),
        ("UNIQUE (storage_url)", "UNIQUE (owner_user_id)"),
        ("ON DELETE SET NULL", "ON DELETE CASCADE"),
        ("USING btree (owner_user_id)", "USING btree (news_id)"),
    ],
)
def test_news_media_asset_contract_rejects_schema_drift(
    monkeypatch: pytest.MonkeyPatch, before: str, after: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_news_media_asset_ddl(operations.statements)
    changed = [
        sql.replace(before, after) if "news_media_assets" in sql else sql
        for sql in operations.statements
    ]
    assert changed != operations.statements
    with pytest.raises(AssertionError):
        _assert_news_media_asset_ddl(changed)


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_news_media_asset_contract_rejects_missing_or_duplicate_statements(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_news_media_asset_ddl(operations.statements)
    for statement in table_statements(operations.statements, "news_media_assets"):
        changed = list(operations.statements)
        if mutation == "missing":
            changed.remove(statement)
        else:
            changed.append(statement)
        with pytest.raises(AssertionError):
            _assert_news_media_asset_ddl(changed)


def test_baseline_rejects_non_postgres_before_catalog_access_or_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = bind_baseline(monkeypatch, dialect="sqlite")
    with pytest.raises(RuntimeError, match=r"^The MVP baseline requires PostgreSQL\.$"):
        migration.upgrade()
    assert operations.bind_requests == 1
    assert operations.bind.reads == []
    assert operations.statements == []


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
