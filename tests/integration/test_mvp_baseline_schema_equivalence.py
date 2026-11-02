"""Prove the MVP baseline reproduces the pre-squash PostgreSQL schema.

The pre-squash chain (``alembic/`` and ``app/`` at commit 3ff5375fb, extracted with
``git archive`` and never checked out) and the baseline revision run against two
PostgreSQL databases. Only the statements and catalog rows listed below may differ,
compared exactly: the AUD-269 restored indexes, the AUD-272 claim ledger, the partition
children of the restored index, and the owner-decided removal of ``ix_users_email_lower``.
Statements are compared after collapsing whitespace, since ``pg_dump`` wraps long
statements. Other catalog facts that ``pg_dump`` omits must be identical, and
``alembic_version`` is the only other allowed difference. Both databases are then
checked against the models, and the baseline must refuse its downgrade without changing
the schema.
"""

from __future__ import annotations

import asyncio
import io
import os
import secrets
import shutil
import sys
import tarfile
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest
import sqlalchemy as sa
from testcontainers.community.postgres import PostgresContainer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRE_SQUASH_COMMIT = "3ff5375fba01b6ff6f2bc18aaf2d6b2ba18e19c9"
PRE_SQUASH_HEAD = "202610310001"
BASELINE_REVISION = "202611020000"
BASELINE_FILE = f"{BASELINE_REVISION}_mvp_baseline.py"
PG_IMAGE = "pgvector/pgvector:pg17@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d"

_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]

# Bounded wall-clock budgets for every child process. A timed-out child is killed and
# reaped before its TimeoutError escapes, so no harness step can wait forever.
_CHILD_TIMEOUT_SECONDS: Final = 240.0
_CHILD_REAP_SECONDS: Final = 30.0

# Environment names that can select another database or an env file in a child process.
# Windows folds environment names to upper case and POSIX keeps them distinct, so every
# spelling is matched case-insensitively and removed before the owned URL is installed.
_SHADOWED_ENVIRONMENT_NAMES: Final = frozenset(
    {"database_url", "database_url_file", "env_file_path"}
)

_RESOLVED_URL_SCRIPT: Final = (
    "from app.core.migration_settings import load_migration_settings, "
    "resolve_migration_url\n"
    "print('RESOLVED_URL=' + resolve_migration_url(load_migration_settings(), "
    "ini_url=None))\n"
)

# The 3 claim-ledger statements, the 8 restored AUD-269 parent indexes and the 26
# partition children (index and ATTACH) are the only statements the baseline adds.
_DELIVERY_ONCE_STATEMENTS: Final = (
    (
        "CREATE TABLE public.notification_delivery_once (\n"
        "    id uuid NOT NULL,\n"
        "    notification_id uuid NOT NULL,\n"
        "    subscription_id uuid,\n"
        "    channel character varying(50) NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL\n"
        ")"
    ),
    (
        "ALTER TABLE ONLY public.notification_delivery_once ADD CONSTRAINT "
        "notification_delivery_once_pkey PRIMARY KEY (id)"
    ),
    (
        "ALTER TABLE ONLY public.notification_delivery_once ADD CONSTRAINT "
        "uq_notification_delivery_once_claim UNIQUE NULLS NOT DISTINCT "
        "(notification_id, subscription_id, channel)"
    ),
)
_RESTORED_PARENT_INDEXES: Final = (
    "CREATE UNIQUE INDEX ux_users_lower_email ON public.users USING btree "
    "(lower((email)::text))",
    "CREATE INDEX ix_user_profiles_full_name_lower ON public.user_profiles USING "
    "btree (lower((full_name)::text) text_pattern_ops) WHERE (full_name IS NOT NULL)",
    "CREATE INDEX ix_user_profiles_full_name_trgm ON public.user_profiles USING "
    "gin (full_name public.gin_trgm_ops) WHERE (full_name IS NOT NULL)",
    "CREATE INDEX idx_notifications_user_unread_created ON ONLY public.notifications "
    "USING btree (user_id, created_at DESC) WHERE (read = false)",
    "CREATE INDEX idx_messages_chat_created ON public.messages USING btree "
    "(chat_id, created_at DESC)",
    "CREATE INDEX ix_stored_events_pending ON public.stored_events USING btree "
    "(status, created_at)",
    "CREATE INDEX idx_active_sessions_user_valid ON public.active_sessions USING "
    "btree (user_id, revoked_at) WHERE (revoked_at IS NULL)",
    "CREATE INDEX ix_active_sessions_user_active_created ON public.active_sessions "
    "USING btree (user_id, created_at) WHERE (revoked_at IS NULL)",
)
_PARTITION_SUFFIXES: Final = (
    "2026_05",
    "2026_06",
    "2026_07",
    "2026_08",
    "2026_09",
    "2026_10",
    "2026_11",
    "2026_12",
    "2027_01",
    "2027_02",
    "2027_03",
    "2027_04",
    "2027_05",
    "2027_06",
    "2027_07",
    "2027_08",
    "2027_09",
    "2027_10",
    "2027_11",
    "2027_12",
    "2028_01",
    "2028_02",
    "2028_03",
    "2028_04",
    "2028_05",
    "default",
)
APPROVED_ADDED_STATEMENTS: Final = (
    *_DELIVERY_ONCE_STATEMENTS,
    *_RESTORED_PARENT_INDEXES,
    *(
        statement
        for suffix in _PARTITION_SUFFIXES
        for statement in (
            f"CREATE INDEX notifications_{suffix}_user_id_created_at_idx1 ON "
            f"public.notifications_{suffix} USING btree (user_id, created_at DESC) "
            "WHERE (read = false)",
            "ALTER INDEX public.idx_notifications_user_unread_created ATTACH PARTITION "
            f"public.notifications_{suffix}_user_id_created_at_idx1",
        )
    ),
)
# Owner decision: keep exactly one unique lower(email) index. The pre-squash
# ix_users_email_lower is dropped; the restored ux_users_lower_email replaces it.
APPROVED_REMOVED_STATEMENTS: Final = (
    "CREATE UNIQUE INDEX ix_users_email_lower ON public.users USING btree "
    "(lower((email)::text))",
)

_DELIVERY_ONCE_RELATION: Final = (
    "notification_delivery_once",
    "r",
    False,
    False,
    False,
    "p",
    "d",
    "",
)
_DELIVERY_ONCE_COLUMNS: Final = (
    ("id", None, "NO", "uuid", None),
    ("notification_id", None, "NO", "uuid", None),
    ("subscription_id", None, "YES", "uuid", None),
    ("channel", None, "NO", "character varying", 50),
    ("created_at", "now()", "NO", "timestamp with time zone", None),
)
# Catalog rows the baseline adds on purpose, in the repr form produced by _probe.
APPROVED_CATALOG_ADDITIONS: Final[Mapping[str, tuple[str, ...]]] = {
    "relations": (repr(_DELIVERY_ONCE_RELATION),),
    "columns": tuple(
        repr(
            (
                "notification_delivery_once",
                name,
                default,
                nullable,
                data_type,
                length,
                None,
                None,
            )
        )
        for name, default, nullable, data_type, length in _DELIVERY_ONCE_COLUMNS
    ),
    # Index inheritance appears in pg_inherits with no table partition bound.
    "partition_bounds": tuple(
        repr(
            (
                f"notifications_{suffix}_user_id_created_at_idx1",
                "idx_notifications_user_unread_created",
                None,
            )
        )
        for suffix in _PARTITION_SUFFIXES
    ),
}

CATALOG_PROBES: dict[str, str] = {
    "roles": (
        "SELECT rolname, rolcanlogin, rolsuper, rolinherit, rolcreaterole, rolcreatedb,"
        " rolbypassrls, rolconnlimit, rolreplication FROM pg_roles"
        " WHERE rolname NOT LIKE 'pg\\_%'"
    ),
    "role_memberships": (
        "SELECT roleid::regrole::text, member::regrole::text, admin_option"
        " FROM pg_auth_members"
    ),
    "extensions": (
        "SELECT extname, extversion, extnamespace::regnamespace::text FROM pg_extension"
    ),
    "relations": (
        "SELECT c.relname, c.relkind, c.relrowsecurity, c.relforcerowsecurity,"
        " c.relispartition, c.relpersistence, c.relreplident, coalesce(c.reloptions::text, '')"
        " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')"
    ),
    "partition_bounds": (
        "SELECT c.relname, p.relname, pg_get_expr(c.relpartbound, c.oid)"
        " FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid"
        " JOIN pg_class p ON p.oid = i.inhparent"
        " JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public'"
    ),
    "policies": (
        "SELECT tablename, policyname, permissive, roles::text, cmd, qual, with_check"
        " FROM pg_policies"
    ),
    "triggers": (
        "SELECT c.relname, t.tgname, t.tgenabled, t.tgisinternal, t.tgtype, p.proname"
        " FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid"
        " JOIN pg_proc p ON p.oid = t.tgfoid JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE NOT t.tgisinternal AND n.nspname = 'public'"
    ),
    "functions": (
        "SELECT p.proname, md5(p.prosrc), p.prolang, p.provolatile, p.prosecdef,"
        " p.proconfig::text, pg_get_function_identity_arguments(p.oid)"
        " FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
        " WHERE n.nspname = 'public'"
    ),
    "sequences": (
        "SELECT sequencename, data_type, start_value, min_value, max_value,"
        " increment_by, cycle, cache_size FROM pg_sequences"
    ),
    "columns": (
        "SELECT table_name, column_name, column_default, is_nullable, data_type,"
        " character_maximum_length, numeric_precision, collation_name"
        " FROM information_schema.columns WHERE table_schema = 'public'"
        " AND table_name <> 'alembic_version'"
    ),
    "acls": (
        "SELECT 'rel', relname, relacl::text FROM pg_class c"
        " JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = 'public' AND relacl IS NOT NULL"
        " UNION ALL SELECT 'proc', proname, proacl::text FROM pg_proc"
        " WHERE proacl IS NOT NULL AND pronamespace = 'public'::regnamespace"
        " UNION ALL SELECT 'nsp', nspname, nspacl::text FROM pg_namespace"
        " WHERE nspname = 'public'"
        " UNION ALL SELECT 'defacl', defaclobjtype::text, defaclacl::text"
        " FROM pg_default_acl"
    ),
    "misc": (
        "SELECT 'evtrig', evtname FROM pg_event_trigger"
        " UNION ALL SELECT 'pub', pubname FROM pg_publication"
        " UNION ALL SELECT 'stat', stxname FROM pg_statistic_ext"
        " UNION ALL SELECT 'rule', rulename FROM pg_rules WHERE schemaname = 'public'"
        " UNION ALL SELECT 'type', typname FROM pg_type t JOIN pg_namespace n"
        " ON n.oid = t.typnamespace WHERE n.nspname = 'public' AND t.typtype <> 'c'"
        " AND t.typname NOT LIKE '\\_%'"
    ),
}


def _loopback_url(container: PostgresContainer, driver: str) -> str:
    """Return the container URL on 127.0.0.1; ``localhost`` tries IPv6 first on Windows."""
    port = container.get_exposed_port(5432)
    return (
        f"postgresql+{driver}://{container.username}:{container.password}"
        f"@127.0.0.1:{port}/{container.dbname}"
    )


@dataclass(frozen=True)
class _Database:
    container: PostgresContainer
    url: str

    @property
    def sync_url(self) -> str:
        return _loopback_url(self.container, "psycopg")


@dataclass(frozen=True)
class _Built:
    pre_squash: _Database
    baseline: _Database
    pre_squash_tree: Path
    baseline_tree: Path


@dataclass(frozen=True)
class _Completed:
    returncode: int
    stdout: str
    stderr: str


async def _run_fixed_argv(
    argv: list[str], cwd: Path, env: dict[str, str] | None = None
) -> tuple[int, bytes, bytes]:
    """Run a fixed argv without a shell and bound its wall-clock time."""
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=_CHILD_TIMEOUT_SECONDS
        )
    except TimeoutError:
        process.kill()
        await asyncio.wait_for(process.wait(), timeout=_CHILD_REAP_SECONDS)
        raise
    return process.returncode or 0, stdout, stderr


def _child_environment(url: str) -> dict[str, str]:
    """Return the child environment in which the owned URL is the only database source."""
    environment = {
        name: value
        for name, value in os.environ.items()
        if name.casefold() not in _SHADOWED_ENVIRONMENT_NAMES
    }
    environment.pop("PYTHONPATH", None)
    environment.update(
        DATABASE_URL=url,
        ENV_FILE_PATH="",
        SECRET_KEY=secrets.token_urlsafe(48),
        ENVIRONMENT="testing",
    )
    return environment


def _extract_pre_squash_tree(target: Path) -> None:
    """Materialize alembic/ and app/ at the pre-squash commit without a checkout."""
    git = shutil.which("git")
    assert git is not None, "git is required to extract the pre-squash chain"
    returncode, archive, stderr = asyncio.run(
        _run_fixed_argv(
            [
                git,
                "archive",
                "--format=tar",
                PRE_SQUASH_COMMIT,
                "alembic",
                "app",
                "alembic.ini",
            ],
            PROJECT_ROOT,
        )
    )
    assert returncode == 0, stderr.decode("utf-8", errors="replace")
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(target, filter="data")


def _extract_baseline_tree(target: Path) -> None:
    """Copy the working-tree app and alembic, keeping only the baseline revision."""
    ignore = shutil.ignore_patterns("__pycache__")
    shutil.copytree(PROJECT_ROOT / "alembic", target / "alembic", ignore=ignore)
    shutil.copytree(PROJECT_ROOT / "app", target / "app", ignore=ignore)
    shutil.copy(PROJECT_ROOT / "alembic.ini", target / "alembic.ini")
    versions = target / "alembic" / "versions"
    for migration in versions.glob("*.py"):
        if migration.name != BASELINE_FILE:
            migration.unlink()


def _alembic(tree: Path, url: str, *args: str) -> _Completed:
    """Run the tree's own Alembic CLI so its ``app`` package is the one imported."""
    returncode, stdout, stderr = asyncio.run(
        _run_fixed_argv(
            [sys.executable, "-m", "alembic", *args], tree, _child_environment(url)
        )
    )
    return _Completed(
        returncode,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def _assert_owned_url_is_authoritative(tree: Path, url: str) -> None:
    """Fail before any DDL unless the child resolves exactly the owned database URL."""
    returncode, stdout, stderr = asyncio.run(
        _run_fixed_argv(
            [sys.executable, "-c", _RESOLVED_URL_SCRIPT],
            tree,
            _child_environment(url),
        )
    )
    diagnostic = stderr.decode("utf-8", errors="replace")[-4000:]
    assert returncode == 0, diagnostic
    resolved = [
        line.removeprefix("RESOLVED_URL=")
        for line in stdout.decode("utf-8", errors="replace").splitlines()
        if line.startswith("RESOLVED_URL=")
    ]
    assert resolved == [url], diagnostic


def _canonical(statement: str) -> str:
    """Collapse layout only: pg_dump wraps statements without changing their SQL."""
    return " ".join(statement.split())


def _split_sql(text: str) -> list[str]:
    """Split pg_dump output on top-level semicolons, honouring quotes and $$ bodies."""
    statements: list[str] = []
    buffer: list[str] = []
    in_quote = False
    in_dollar = False
    index = 0
    while index < len(text):
        if not in_quote and text.startswith("$$", index):
            in_dollar = not in_dollar
            buffer.append("$$")
            index += 2
            continue
        char = text[index]
        if not in_dollar and char == "'":
            in_quote = not in_quote
        if char == ";" and not in_quote and not in_dollar:
            statements.append("".join(buffer).strip())
            buffer = []
        else:
            buffer.append(char)
        index += 1
    statements.append("".join(buffer).strip())
    return [statement for statement in statements if statement]


def _schema_statements(dump: str) -> Counter[str]:
    kept = [
        line
        for line in dump.splitlines()
        if not line.startswith(("--", "\\", "SET ", "SELECT pg_catalog.set_config"))
    ]
    return Counter(_canonical(statement) for statement in _split_sql("\n".join(kept)))


def _dump(database: _Database) -> str:
    container = database.container.get_wrapped_container()
    exit_code, output = container.exec_run(
        [
            "pg_dump",
            "--schema-only",
            "--no-owner",
            "--no-privileges",
            "-U",
            database.container.username,
            "-d",
            database.container.dbname,
        ]
    )
    assert exit_code == 0, output.decode("utf-8", errors="replace")
    return output.decode("utf-8")


def _probe(database: _Database) -> dict[str, list[str]]:
    engine = sa.create_engine(database.sync_url)
    try:
        with engine.connect() as connection:
            results: dict[str, list[str]] = {}
            for name, query in CATALOG_PROBES.items():
                rows = connection.execute(sa.text(query)).all()
                results[name] = sorted(repr(tuple(row)) for row in rows)
            return results
    finally:
        engine.dispose()


def _version(database: _Database) -> list[str]:
    engine = sa.create_engine(database.sync_url)
    try:
        with engine.connect() as connection:
            return [
                str(row[0])
                for row in connection.execute(
                    sa.text("SELECT version_num FROM alembic_version")
                )
            ]
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Iterator[_Built]:
    """Apply the pre-squash chain and the baseline to two fresh PostgreSQL servers."""
    pre_squash_tree = tmp_path_factory.mktemp("pre_squash")
    baseline_tree = tmp_path_factory.mktemp("baseline")
    _extract_pre_squash_tree(pre_squash_tree)
    _extract_baseline_tree(baseline_tree)

    with (
        PostgresContainer(PG_IMAGE) as pre_container,
        PostgresContainer(PG_IMAGE) as baseline_container,
    ):
        pre = _Database(pre_container, _loopback_url(pre_container, "asyncpg"))
        base = _Database(
            baseline_container, _loopback_url(baseline_container, "asyncpg")
        )

        # The baseline must resolve the owned URL before its first DDL statement runs. The
        # pre-squash oracle predates app.core.migration_settings; its env.py returns the
        # DATABASE_URL environment value first, which _child_environment supplies.
        _assert_owned_url_is_authoritative(baseline_tree, base.url)

        upgraded_pre = _alembic(pre_squash_tree, pre.url, "upgrade", "head")
        assert upgraded_pre.returncode == 0, upgraded_pre.stderr[-4000:]
        upgraded_base = _alembic(baseline_tree, base.url, "upgrade", "head")
        assert upgraded_base.returncode == 0, upgraded_base.stderr[-4000:]

        yield _Built(pre, base, pre_squash_tree, baseline_tree)


def test_pre_squash_chain_and_baseline_stamp_their_own_heads(built: _Built) -> None:
    assert _version(built.pre_squash) == [PRE_SQUASH_HEAD]
    assert _version(built.baseline) == [BASELINE_REVISION]


def test_statement_level_schema_differs_only_by_the_audited_additions(
    built: _Built,
) -> None:
    before = _schema_statements(_dump(built.pre_squash))
    after = _schema_statements(_dump(built.baseline))

    assert before - after == Counter(
        _canonical(statement) for statement in APPROVED_REMOVED_STATEMENTS
    )
    assert after - before == Counter(
        _canonical(statement) for statement in APPROVED_ADDED_STATEMENTS
    )


def test_catalog_facts_outside_the_additions_are_identical(built: _Built) -> None:
    before = _probe(built.pre_squash)
    after = _probe(built.baseline)

    assert before.keys() == after.keys() == CATALOG_PROBES.keys()
    for name in CATALOG_PROBES:
        assert not Counter(before[name]) - Counter(after[name]), name
        added = Counter(after[name]) - Counter(before[name])
        assert added == Counter(APPROVED_CATALOG_ADDITIONS.get(name, ())), name


def test_baseline_database_matches_the_current_models(built: _Built) -> None:
    result = _alembic(built.baseline_tree, built.baseline.url, "check")

    assert result.returncode == 0, result.stderr[-4000:]


def test_baseline_refuses_downgrade_and_keeps_its_revision(built: _Built) -> None:
    result = _alembic(built.baseline_tree, built.baseline.url, "downgrade", "base")

    assert result.returncode != 0
    assert "cannot be downgraded" in result.stderr
    assert _version(built.baseline) == [BASELINE_REVISION]
