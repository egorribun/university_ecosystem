"""Prove the MVP baseline reproduces the pre-squash PostgreSQL schema.

The pre-squash chain (``alembic/`` and ``app/`` at commit 3ff5375fb, extracted with
``git archive`` and never checked out) runs against one PostgreSQL database. The
baseline revision runs against a second database. Only the AUD-269 and AUD-272
additions may differ, plus the one owner-decided removal of the duplicate unique
``lower(email)`` index ``ix_users_email_lower``, which ``ux_users_lower_email``
replaces. Statement-level ``pg_dump --schema-only`` must show no other removed
statement and only additions that name those objects, and the catalog facts that
``pg_dump`` omits (roles, policies, triggers, functions, sequences, partitions, ACLs,
extensions) must be identical outside those objects. ``alembic_version`` is the only
other allowed difference. Both databases are then checked against the models, and the
baseline must refuse its downgrade without changing the schema.
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import shutil
import sys
import tarfile
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import sqlalchemy as sa
from testcontainers.community.postgres import PostgresContainer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRE_SQUASH_COMMIT = "3ff5375fba01b6ff6f2bc18aaf2d6b2ba18e19c9"
PRE_SQUASH_HEAD = "202610310001"
BASELINE_REVISION = "202611020000"
BASELINE_FILE = f"{BASELINE_REVISION}_mvp_baseline.py"
PG_IMAGE = "pgvector/pgvector:pg17@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d"  # pragma: allowlist secret

_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]

# Every object the baseline adds on purpose: the AUD-269 restored indexes, the AUD-272
# claim ledger, and the partition children that PostgreSQL creates for the restored
# notifications index. A statement outside this pattern is a schema drift.
ADDITION_PATTERN = re.compile(
    r"notification_delivery_once|uq_notification_delivery_once_claim"
    r"|ux_users_lower_email|ix_user_profiles_full_name_lower|ix_user_profiles_full_name_trgm"
    r"|idx_messages_chat_created|idx_notifications_user_unread_created"
    r"|ix_stored_events_pending\b|idx_active_sessions_user_valid"
    r"|ix_active_sessions_user_active_created"
    r"|notifications_(?:\d{4}_\d{2}|default)_user_id_created_at_idx1"
)
# 3 delivery-once statements, 1 unique restored index, 7 restored non-unique parents,
# 26 notifications partition indexes and their 26 ATTACH statements.
EXPECTED_ADDED_STATEMENTS = 63
# Owner decision: keep exactly one unique lower(email) index. The pre-squash
# ix_users_email_lower is dropped; the restored ux_users_lower_email replaces it.
REMOVED_PATTERN = re.compile(r"CREATE UNIQUE INDEX ix_users_email_lower\b")
EXPECTED_REMOVED_STATEMENTS = 1

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
    """Run a fixed argv without a shell; no argument is derived from untrusted input."""
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return process.returncode or 0, stdout, stderr


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
    env = {
        **os.environ,
        "DATABASE_URL": url,
        "SECRET_KEY": "mvp-baseline-equivalence-dummy-secret-key-0123456789",  # pragma: allowlist secret
        "ENVIRONMENT": "testing",
    }
    env.pop("PYTHONPATH", None)
    returncode, stdout, stderr = asyncio.run(
        _run_fixed_argv([sys.executable, "-m", "alembic", *args], tree, env)
    )
    return _Completed(
        returncode,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


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
    return Counter(_split_sql("\n".join(kept)))


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

    removed = before - after
    added = after - before

    unexpected_removals = [
        statement for statement in removed if not REMOVED_PATTERN.search(statement)
    ]
    assert not unexpected_removals, unexpected_removals[:5]
    assert sum(removed.values()) == EXPECTED_REMOVED_STATEMENTS
    unexpected = [
        statement for statement in added if not ADDITION_PATTERN.search(statement)
    ]
    assert not unexpected, unexpected[:5]
    assert sum(added.values()) == EXPECTED_ADDED_STATEMENTS


def test_catalog_facts_outside_the_additions_are_identical(built: _Built) -> None:
    before = _probe(built.pre_squash)
    after = _probe(built.baseline)

    assert before.keys() == after.keys()
    for name in CATALOG_PROBES:
        left = [row for row in before[name] if not ADDITION_PATTERN.search(row)]
        right = [row for row in after[name] if not ADDITION_PATTERN.search(row)]
        assert left == right, name
    # The additions must be present in the baseline and absent from the old chain.
    assert any("notification_delivery_once" in row for row in after["relations"])
    assert not any("notification_delivery_once" in row for row in before["relations"])


def test_baseline_database_matches_the_current_models(built: _Built) -> None:
    result = _alembic(built.baseline_tree, built.baseline.url, "check")

    assert result.returncode == 0, result.stderr[-4000:]


def test_baseline_refuses_downgrade_and_keeps_its_revision(built: _Built) -> None:
    result = _alembic(built.baseline_tree, built.baseline.url, "downgrade", "base")

    assert result.returncode != 0
    assert "cannot be downgraded" in result.stderr
    assert _version(built.baseline) == [BASELINE_REVISION]
