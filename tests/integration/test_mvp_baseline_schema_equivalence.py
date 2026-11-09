"""Prove the MVP baseline reproduces the pre-squash PostgreSQL schema.

The pre-squash chain (``alembic/`` and ``app/`` at commit 3ff5375fb, extracted with
``git archive`` and never checked out) and the baseline revision run against two
PostgreSQL databases. Only the statements and catalog rows listed below may differ,
compared exactly: the AUD-269 restored indexes, the AUD-272 claim ledger, the partition
children of the restored index, the approved ix-to-ux email-index replacement
(owner approval recorded 2026-11-05 UTC), and
the AUD-272 removal of the redundant ``uq_notification_delivery_once`` constraint.
Statements are compared after collapsing unquoted layout, since ``pg_dump`` wraps
long statements; quoted values and function bodies remain byte-sensitive. Other catalog facts that ``pg_dump`` omits must be identical, and
``alembic_version`` is the only other allowed difference. The baseline is then
checked against the current models and must refuse its downgrade without changing
the schema.
"""

from __future__ import annotations

import ast
import asyncio
import io
import os
import re
import secrets
import shutil
import sys
import tarfile
import time
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from tests.fixtures import owned_baseline_postgres as owned

initialize_database_for_tests = owned.initialize_database_for_tests
prepare_database = owned.prepare_database
clean_database = owned.clean_database
default_database_guard = owned.default_database_guard

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRE_SQUASH_COMMIT = "3ff5375fba01b6ff6f2bc18aaf2d6b2ba18e19c9"
PRE_SQUASH_HEAD = "202610310001"
BASELINE_REVISION = "202611020000"
BASELINE_FILE = f"{BASELINE_REVISION}_mvp_baseline.py"
_RUN = os.getenv("RUN_INTEGRATION_TESTS") == "1"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]

# Bound direct-child communication and cleanup separately. Cancellation also kills
# and drains the direct child; failed cleanup remains an error, not proof of reaping.
# These budgets do not claim ownership or termination of independently spawned children.
_CHILD_TIMEOUT_SECONDS: Final = 240.0
_CHILD_REAP_SECONDS: Final = 30.0
_DUMP_SECONDS: Final = 120.0

# Inherit operating-system launch essentials only. Runtime settings, file-secret
# selectors, Python import overrides and CI exemptions must never select another target.
_CHILD_OPERATING_SYSTEM_NAMES: Final = frozenset(
    {"path", "systemroot", "windir", "temp", "tmp", "tmpdir"}
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
# Owner decision, 2026-11-03 (approved in chat): exactly one audited replacement of
# the messages_participant_isolation policy. The NULLIF form makes an unbound pooled
# session deny with zero rows, instead of raising 22P02 (invalid_text_representation),
# after a transaction-local app.current_user_id has ended and reads as ''. ADR-051
# records the same approval.
_MESSAGES_PARTICIPANT_STATEMENT_BEFORE: Final = (
    "CREATE POLICY messages_participant_isolation ON public.messages USING "
    "((chat_id IN ( SELECT chat_participants.chat_id FROM public.chat_participants "
    "WHERE (chat_participants.user_id = "
    "(current_setting('app.current_user_id'::text, true))::uuid))))"
)
_MESSAGES_PARTICIPANT_STATEMENT_AFTER: Final = (
    "CREATE POLICY messages_participant_isolation ON public.messages USING "
    "((chat_id IN ( SELECT chat_participants.chat_id FROM public.chat_participants "
    "WHERE (chat_participants.user_id = "
    "(NULLIF(current_setting('app.current_user_id'::text, true), ''::text))::uuid))))"
)
_MESSAGES_PARTICIPANT_QUAL_BEFORE: Final = (
    "(chat_id IN ( SELECT chat_participants.chat_id\n   FROM chat_participants\n"
    "  WHERE (chat_participants.user_id = "
    "(current_setting('app.current_user_id'::text, true))::uuid)))"
)
_MESSAGES_PARTICIPANT_QUAL_AFTER: Final = (
    "(chat_id IN ( SELECT chat_participants.chat_id\n   FROM chat_participants\n"
    "  WHERE (chat_participants.user_id = "
    "(NULLIF(current_setting('app.current_user_id'::text, true), ''::text))::uuid)))"
)
# repr() of the pg_policies row, as _probe() produces it.
_MESSAGES_PARTICIPANT_ROW_BEFORE: Final = repr(
    (
        "messages",
        "messages_participant_isolation",
        "PERMISSIVE",
        "{public}",
        "ALL",
        _MESSAGES_PARTICIPANT_QUAL_BEFORE,
        None,
    )
)
_MESSAGES_PARTICIPANT_ROW_AFTER: Final = repr(
    (
        "messages",
        "messages_participant_isolation",
        "PERMISSIVE",
        "{public}",
        "ALL",
        _MESSAGES_PARTICIPANT_QUAL_AFTER,
        None,
    )
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
    _MESSAGES_PARTICIPANT_STATEMENT_AFTER,
)
# Owner decision, 2026-11-04 (approved in chat), AUD-272: the redundant
# uq_notification_delivery_once UNIQUE (notification_id, channel, subscription_id,
# attempted_at) constraint is removed from notification_deliveries. Delivery-once is
# enforced by the claim ledger keyed on (notification_id, subscription_id, channel).
# PostgreSQL built the constraint on the parent and on each partition (suffix, generated
# child constraint name) and attached each child index to the parent index. Those are the
# only statements that disappear for this change, in the pre-squash dump form.
_DELIVERY_ONCE_REMOVED_PARTITIONS: Final = (
    ("2026_05", "notification_deliveries_2026__notification_id_channel_subsc_key"),
    ("2026_06", "notification_deliveries_2026__notification_id_channel_subs_key1"),
    ("2026_07", "notification_deliveries_2026__notification_id_channel_subs_key2"),
    ("2026_08", "notification_deliveries_2026__notification_id_channel_subs_key3"),
    ("2026_09", "notification_deliveries_2026__notification_id_channel_subs_key4"),
    ("2026_10", "notification_deliveries_2026__notification_id_channel_subs_key5"),
    ("2026_11", "notification_deliveries_2026__notification_id_channel_subs_key6"),
    ("2026_12", "notification_deliveries_2026__notification_id_channel_subs_key7"),
    ("2027_01", "notification_deliveries_2027__notification_id_channel_subsc_key"),
    ("2027_02", "notification_deliveries_2027__notification_id_channel_subs_key1"),
    ("2027_03", "notification_deliveries_2027__notification_id_channel_subs_key2"),
    ("2027_04", "notification_deliveries_2027__notification_id_channel_subs_key3"),
    ("2027_05", "notification_deliveries_2027__notification_id_channel_subs_key4"),
    ("2027_06", "notification_deliveries_2027__notification_id_channel_subs_key5"),
    ("2027_07", "notification_deliveries_2027__notification_id_channel_subs_key6"),
    ("2027_08", "notification_deliveries_2027__notification_id_channel_subs_key7"),
    ("2027_09", "notification_deliveries_2027__notification_id_channel_subs_key8"),
    ("2027_10", "notification_deliveries_2027__notification_id_channel_subs_key9"),
    ("2027_11", "notification_deliveries_2027_notification_id_channel_subs_key10"),
    ("2027_12", "notification_deliveries_2027_notification_id_channel_subs_key11"),
    ("2028_01", "notification_deliveries_2028__notification_id_channel_subsc_key"),
    ("2028_02", "notification_deliveries_2028__notification_id_channel_subs_key1"),
    ("2028_03", "notification_deliveries_2028__notification_id_channel_subs_key2"),
    ("2028_04", "notification_deliveries_2028__notification_id_channel_subs_key3"),
    ("2028_05", "notification_deliveries_2028__notification_id_channel_subs_key4"),
    ("default", "notification_deliveries_defau_notification_id_channel_subsc_key"),
)
_DELIVERY_ONCE_REMOVED_STATEMENTS: Final = (
    "ALTER TABLE ONLY public.notification_deliveries\n"
    "    ADD CONSTRAINT uq_notification_delivery_once UNIQUE (notification_id, "
    "channel, subscription_id, attempted_at)",
    *(
        statement
        for suffix, child in _DELIVERY_ONCE_REMOVED_PARTITIONS
        for statement in (
            f"ALTER TABLE ONLY public.notification_deliveries_{suffix}\n"
            f"    ADD CONSTRAINT {child} UNIQUE (notification_id, channel, "
            "subscription_id, attempted_at)",
            "ALTER INDEX public.uq_notification_delivery_once ATTACH PARTITION "
            f"public.{child}",
        )
    ),
)
# Provenance: the 2026-11-01 AUD269 review records ux_users_lower_email as
# source-equivalent to ix_users_email_lower (UNIQUE lower(email)).
# ADR-051 records owner approval of this exact replacement (2026-11-05 UTC).
# This is storage-schema provenance only. The pinned pre-squash service handles
# both names; current error mapping handles ux_users_lower_email but not
# ix_users_email_lower. No cross-revision application error-diagnostic
# equivalence is claimed.
APPROVED_REMOVED_STATEMENTS: Final = (
    "CREATE UNIQUE INDEX ix_users_email_lower ON public.users USING btree "
    "(lower((email)::text))",
    _MESSAGES_PARTICIPANT_STATEMENT_BEFORE,
    *_DELIVERY_ONCE_REMOVED_STATEMENTS,
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
# Stable pg_index projection for the exact AUD-269 index-name replacement.
_USER_EMAIL_INDEX_BEFORE: Final = repr(
    (
        "users",
        "ix_users_email_lower",
        "btree",
        True,
        True,
        True,
        True,
        False,
        "CREATE UNIQUE INDEX ix_users_email_lower ON public.users USING btree "
        "(lower((email)::text))",
    )
)
_USER_EMAIL_INDEX_AFTER: Final = repr(
    (
        "users",
        "ux_users_lower_email",
        "btree",
        True,
        True,
        True,
        True,
        False,
        "CREATE UNIQUE INDEX ux_users_lower_email ON public.users USING btree "
        "(lower((email)::text))",
    )
)
# Catalog rows the baseline adds on purpose, in the repr form produced by _probe.
APPROVED_CATALOG_ADDITIONS: Final[Mapping[str, tuple[str, ...]]] = {
    "policies": (_MESSAGES_PARTICIPANT_ROW_AFTER,),
    "user_email_indexes": (_USER_EMAIL_INDEX_AFTER,),
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

# Catalog rows the replacement above removes, and the AUD-272 constraint removal.
# The constraint's index inheritance rows disappear from pg_inherits as well.
APPROVED_CATALOG_REMOVALS: Final[Mapping[str, tuple[str, ...]]] = {
    "policies": (_MESSAGES_PARTICIPANT_ROW_BEFORE,),
    "user_email_indexes": (_USER_EMAIL_INDEX_BEFORE,),
    "partition_bounds": tuple(
        repr((child, "uq_notification_delivery_once", None))
        for _suffix, child in _DELIVERY_ONCE_REMOVED_PARTITIONS
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
    "user_email_indexes": (
        "SELECT table_class.relname, index_class.relname, access_method.amname, "
        "index_info.indisunique, index_info.indisvalid, index_info.indisready, "
        "index_info.indislive, index_info.indisprimary, "
        "pg_get_indexdef(index_info.indexrelid) "
        "FROM pg_index index_info "
        "JOIN pg_class index_class ON index_class.oid = index_info.indexrelid "
        "JOIN pg_class table_class ON table_class.oid = index_info.indrelid "
        "JOIN pg_am access_method ON access_method.oid = index_class.relam "
        "JOIN pg_namespace table_schema ON table_schema.oid = table_class.relnamespace "
        "WHERE table_schema.nspname = 'public' AND table_class.relname = 'users' "
        "AND index_class.relname IN ('ix_users_email_lower', 'ux_users_lower_email')"
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


def _owned_url(server: owned.OwnedPostgres, driver: str) -> str:
    """Return the owned loopback URL without libpq options.

    The container command already sets the server-side lock, statement and idle
    transaction limits, so child processes receive the bare URL.
    """
    return server.url.set(drivername=f"postgresql+{driver}", query={}).render_as_string(
        hide_password=False
    )


@dataclass(frozen=True)
class _Database:
    server: owned.OwnedPostgres
    url: str

    @property
    def sync_url(self) -> str:
        return _owned_url(self.server, "psycopg")


@dataclass(frozen=True)
class _Captured:
    dump: str
    catalog: tuple[tuple[str, tuple[str, ...]], ...]
    version: tuple[str, ...]


@dataclass(frozen=True)
class _Built:
    pre_squash: _Database
    baseline: _Database
    pre_squash_tree: Path
    baseline_tree: Path
    pre_squash_capture: _Captured
    baseline_capture: _Captured


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
    communication = asyncio.create_task(process.communicate())
    try:
        stdout, stderr = await asyncio.wait_for(
            asyncio.shield(communication), timeout=_CHILD_TIMEOUT_SECONDS
        )
    except BaseException as failure:  # Cleanup must also run on caller cancellation.
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                # The direct child may have exited between the returncode check and kill.
                pass
        # A failed communicate task cannot reap the child on a second await.
        # Drain pending pipes and explicitly wait for the direct child together.
        cleanup = asyncio.gather(process.wait(), communication, return_exceptions=True)
        try:
            await asyncio.wait_for(cleanup, timeout=_CHILD_REAP_SECONDS)
        except TimeoutError:
            failure.add_note("schema-proof direct-child cleanup exceeded its deadline")
        finally:
            if not cleanup.done():
                cleanup.cancel()
            await asyncio.gather(cleanup, return_exceptions=True)
        raise
    return process.returncode or 0, stdout, stderr


def _child_environment(url: str) -> dict[str, str]:
    """Return the child environment in which the owned URL is the only database source."""
    environment = {
        name: value
        for name, value in os.environ.items()
        if name.casefold() in _CHILD_OPERATING_SYSTEM_NAMES
    }
    environment.update(
        DATABASE_URL=url,
        ENV_FILE_PATH="",
        SECRET_KEY=secrets.token_urlsafe(48),
        ENVIRONMENT="testing",
        PYTHONNOUSERSITE="1",
        PYTHONUTF8="1",
    )
    if sys.platform == "linux":
        # setup-python installs its shared interpreter library beside the base
        # runtime. Derive that single trusted directory; never copy ambient LD_*.
        environment["LD_LIBRARY_PATH"] = str(Path(sys.base_prefix).resolve() / "lib")
    return environment


def _extract_pre_squash_tree(target: Path) -> None:
    """Materialize alembic/ and app/ at the pre-squash commit without a checkout."""
    git = shutil.which("git")
    assert git is not None, "git is required to extract the pre-squash chain"
    present, _, _ = asyncio.run(
        _run_fixed_argv(
            [git, "cat-file", "-e", f"{PRE_SQUASH_COMMIT}^{{commit}}"], PROJECT_ROOT
        )
    )
    if present != 0:
        pytest.fail(
            f"pinned pre-squash commit {PRE_SQUASH_COMMIT} is absent from this "
            "checkout; fetch it (or use fetch-depth: 0) before the baseline proof",
            pytrace=False,
        )
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


def _sql_tokens(text: str) -> Iterator[str]:
    """Yield layout and SQL tokens without changing quoted values or function bodies.

    This is a fail-closed lexer for pg_dump SQL, not a SQL semantic normalizer.
    Only top-level dump comments and restriction directives are discarded.
    """
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            end = index + 1
            while end < len(text) and text[end].isspace():
                end += 1
            yield text[index:end]
        elif text.startswith("--", index):
            end = text.find("\n", index)
            end = len(text) if end == -1 else end + 1
            yield "\n" if "\n" in text[index:end] else " "
        elif text.startswith("/*", index):
            end, depth = index + 2, 1
            while end < len(text) and depth:
                if text.startswith("/*", end):
                    depth += 1
                    end += 2
                elif text.startswith("*/", end):
                    depth -= 1
                    end += 2
                else:
                    end += 1
            if depth:
                raise ValueError("Unterminated SQL block comment")
            yield "\n" if "\n" in text[index:end] else " "
        elif char in "\"'":
            # pg_dump uses standard-conforming strings; only E-prefixed strings
            # interpret backslash escapes. Doubled quote characters remain literal.
            escaped = (
                char == "'"
                and index > 0
                and text[index - 1] in "eE"
                and (
                    index < 2
                    or not (text[index - 2].isalnum() or text[index - 2] in "_$")
                )
            )
            end = index + 1
            while end < len(text):
                if escaped and text[end] == "\\":
                    end += 2
                elif text[end] == char:
                    if end + 1 < len(text) and text[end + 1] == char:
                        end += 2
                    else:
                        end += 1
                        break
                else:
                    end += 1
            else:
                raise ValueError("Unterminated SQL quoted token")
            yield text[index:end]
        elif char == "$" and (
            index == 0 or not (text[index - 1].isalnum() or text[index - 1] in "_$")
        ):
            match = re.match(r"\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$", text[index:])
            if match is None:
                end = index + 1
                yield char
            else:
                delimiter = match.group()
                end = text.find(delimiter, index + len(delimiter))
                if end == -1:
                    raise ValueError("Unterminated SQL dollar-quoted token")
                end += len(delimiter)
                yield text[index:end]
        elif char == "\\":
            line_start = text.rfind("\n", 0, index) + 1
            if text[line_start:index].strip():
                raise ValueError("Unexpected SQL backslash outside a quoted token")
            end = text.find("\n", index)
            end = len(text) if end == -1 else end + 1
            directive = text[index:end].strip().split()
            if len(directive) != 2 or directive[0] not in {
                r"\restrict",
                r"\unrestrict",
            }:
                raise ValueError("Unexpected pg_dump directive")
            yield " "
        else:
            end = index + 1
            yield char
        index = end


def _canonical(statement: str) -> str:
    """Collapse layout only outside literals, quoted identifiers and function bodies."""
    tokens = list(_sql_tokens(statement))
    result: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        end = index + 1
        if token.isspace():
            contains_newline = "\n" in token
            while end < len(tokens) and tokens[end].isspace():
                contains_newline = contains_newline or "\n" in tokens[end]
                end += 1
            # PostgreSQL concatenates adjacent string constants only if their
            # separating whitespace contains a newline. Preserve that distinction.
            previous = tokens[index - 1] if index else ""
            following = tokens[end] if end < len(tokens) else ""
            token = (
                "\n"
                if previous.startswith("'")
                and following.startswith("'")
                and contains_newline
                else " "
            )
        result.append(token)
        index = end
    return "".join(result).strip()


def _split_sql(text: str) -> list[str]:
    """Split only top-level semicolons; quoted tokens are indivisible."""
    statements: list[str] = []
    buffer: list[str] = []
    for token in _sql_tokens(text):
        if token == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
        else:
            buffer.append(token)
    statement = "".join(buffer).strip()
    if statement:
        statements.append(statement)
    return statements


def _schema_statements(dump: str) -> Counter[str]:
    statements = (_canonical(statement) for statement in _split_sql(dump))
    return Counter(
        statement
        for statement in statements
        if not statement.startswith(("SET ", "SELECT pg_catalog.set_config"))
    )


def _dump(database: _Database) -> str:
    """Run pg_dump inside the owned container and return its schema-only SQL.

    The execution is detached and polled with bounded requests, as in the owned
    role bootstrap; the dump is then read back as a single archived file.
    """
    server = database.server
    lease = server._lease
    client = lease.client
    dump_name = f"schema-{secrets.token_hex(8)}.sql"
    lease.verify(server)
    execution = owned._docker_call(
        lambda: client.exec_create(
            server.container_id,
            cmd=[
                "pg_dump",
                "--schema-only",
                "--no-owner",
                "--no-privileges",
                "--host=/var/run/postgresql",
                "--port=5432",
                "--username=baseline_admin",
                "--no-password",
                "--dbname=postgres",
                f"--file=/root/{dump_name}",
            ],
            environment={"PGCONNECT_TIMEOUT": "5"},
            user="root",
        ),
        "schema dump exec creation",
    )
    execution_id = execution.get("Id")
    if (
        not isinstance(execution_id, str)
        or re.fullmatch(r"[0-9a-f]{64}", execution_id) is None
    ):
        raise owned.OwnedPostgresError("Owned schema dump exec identity unacknowledged")
    lease.verify(server)
    owned._docker_call(
        lambda: client.exec_start(execution_id, detach=True),
        "schema dump detached execution",
    )
    deadline = time.monotonic() + _DUMP_SECONDS
    while True:
        lease.verify(server)
        state = owned._docker_call(
            lambda: client.exec_inspect(execution_id), "schema dump exec inspection"
        )
        if state.get("Running") is False:
            break
        if time.monotonic() >= deadline:
            raise AssertionError("pg_dump exceeded its bounded wait")
        time.sleep(0.25)
    assert state.get("ExitCode") == 0, (
        "pg_dump failed in the owned PostgreSQL container"
    )
    stream, _stat = owned._docker_call(
        lambda: client.get_archive(server.container_id, f"/root/{dump_name}"),
        "schema dump archive retrieval",
    )
    archive = b"".join(stream)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        member = tar.extractfile(dump_name)
        assert member is not None, "pg_dump archive lacks the schema file"
        return member.read().decode("utf-8")


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


def _capture(database: _Database) -> _Captured:
    """Freeze raw evidence before any SQL splitting or approved-delta processing."""
    dump = _dump(database)
    catalog = _probe(database)
    version = _version(database)
    return _Captured(
        dump,
        tuple((name, tuple(rows)) for name, rows in catalog.items()),
        tuple(version),
    )


def _capture_pair(
    pre_squash: _Database, baseline: _Database
) -> tuple[_Captured, _Captured]:
    """Capture both independently built databases before comparing either one."""
    return _capture(pre_squash), _capture(baseline)


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Iterator[_Built]:
    """Apply the pre-squash chain and the baseline to two owned PostgreSQL leases."""
    pre_squash_tree = tmp_path_factory.mktemp("pre_squash")
    baseline_tree = tmp_path_factory.mktemp("baseline")
    _extract_pre_squash_tree(pre_squash_tree)
    _extract_baseline_tree(baseline_tree)

    with (
        owned.owned_postgres_server() as pre_server,
        owned.owned_postgres_server() as baseline_server,
    ):
        pre = _Database(pre_server, _owned_url(pre_server, "asyncpg"))
        base = _Database(baseline_server, _owned_url(baseline_server, "asyncpg"))

        # The baseline must resolve the owned URL before its first DDL statement runs. The
        # pre-squash oracle predates app.core.migration_settings; its env.py returns the
        # DATABASE_URL environment value first, which _child_environment supplies.
        _assert_owned_url_is_authoritative(baseline_tree, base.url)

        upgraded_pre = _alembic(pre_squash_tree, pre.url, "upgrade", "head")
        assert upgraded_pre.returncode == 0, upgraded_pre.stderr[-4000:]
        upgraded_base = _alembic(baseline_tree, base.url, "upgrade", "head")
        assert upgraded_base.returncode == 0, upgraded_base.stderr[-4000:]

        pre_capture, baseline_capture = _capture_pair(pre, base)
        yield _Built(
            pre, base, pre_squash_tree, baseline_tree, pre_capture, baseline_capture
        )


def test_proof_owned_fixture_never_uses_default_database(
    default_database_guard: list[str],
) -> None:
    """Exercise this module's real autouse graph without starting Docker."""
    assert default_database_guard == []


def test_absent_pre_squash_commit_fails_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A shallow checkout reports the missing pin, not a raw git tree error."""
    monkeypatch.setattr(sys.modules[__name__], "PRE_SQUASH_COMMIT", "0" * 40)

    with pytest.raises(pytest.fail.Exception, match="pinned pre-squash commit"):
        _extract_pre_squash_tree(tmp_path)


def test_pre_squash_chain_and_baseline_stamp_their_own_heads(built: _Built) -> None:
    assert built.pre_squash_capture.version == (PRE_SQUASH_HEAD,)
    assert built.baseline_capture.version == (BASELINE_REVISION,)


def test_statement_level_schema_differs_only_by_the_audited_additions(
    built: _Built,
) -> None:
    before = _schema_statements(built.pre_squash_capture.dump)
    after = _schema_statements(built.baseline_capture.dump)

    assert before - after == Counter(
        _canonical(statement) for statement in APPROVED_REMOVED_STATEMENTS
    )
    assert after - before == Counter(
        _canonical(statement) for statement in APPROVED_ADDED_STATEMENTS
    )


def test_catalog_facts_outside_the_additions_are_identical(built: _Built) -> None:
    before = dict(built.pre_squash_capture.catalog)
    after = dict(built.baseline_capture.catalog)

    assert before.keys() == after.keys() == CATALOG_PROBES.keys()
    for name in CATALOG_PROBES:
        removed = Counter(before[name]) - Counter(after[name])
        assert removed == Counter(APPROVED_CATALOG_REMOVALS.get(name, ())), name
        added = Counter(after[name]) - Counter(before[name])
        assert added == Counter(APPROVED_CATALOG_ADDITIONS.get(name, ())), name


def _rls_table_names(relations: tuple[str, ...]) -> frozenset[str]:
    """Return the public relations with row-level security enabled (AUD-277)."""
    rows = (ast.literal_eval(rendered) for rendered in relations)
    return frozenset(row[0] for row in rows if row[2] is True)


def _is_literal_true(expression: str) -> bool:
    return re.sub(r"[\s()]", "", expression).casefold() == "true"


def _unconditional_permissive_policies(
    policies: tuple[str, ...], rls_tables: frozenset[str]
) -> list[str]:
    """Return ``table.policy`` for permissive policies on RLS tables that admit everything.

    A policy is unconditional when its USING or WITH CHECK expression is literally
    ``true``. Restrictive policies and policies on tables without RLS are not counted.
    """
    offenders: list[str] = []
    for rendered in policies:
        table, name, permissive, _roles, _command, qual, with_check = ast.literal_eval(
            rendered
        )
        if table not in rls_tables or permissive != "PERMISSIVE":
            continue
        if any(
            expression is not None and _is_literal_true(expression)
            for expression in (qual, with_check)
        ):
            offenders.append(f"{table}.{name}")
    return offenders


def test_no_permissive_using_true_policy_exists_on_any_rls_table(built: _Built) -> None:
    """AUD-277: the baseline catalog has no RLS policy that admits every row."""
    catalog = dict(built.baseline_capture.catalog)
    rls_tables = _rls_table_names(catalog["relations"])
    assert rls_tables, "the baseline catalog reports no RLS-enabled table"
    assert _unconditional_permissive_policies(catalog["policies"], rls_tables) == []


def test_baseline_database_matches_the_current_models(built: _Built) -> None:
    result = _alembic(built.baseline_tree, built.baseline.url, "check")

    assert result.returncode == 0, result.stderr[-4000:]


def test_baseline_refuses_downgrade_and_keeps_its_revision(built: _Built) -> None:
    result = _alembic(built.baseline_tree, built.baseline.url, "downgrade", "base")

    assert result.returncode != 0
    assert "cannot be downgraded" in result.stderr
    after = _capture(built.baseline)
    assert after.version == built.baseline_capture.version == (BASELINE_REVISION,)
    assert after.catalog == built.baseline_capture.catalog
    assert _schema_statements(after.dump) == _schema_statements(
        built.baseline_capture.dump
    )


def test_baseline_refuses_nonempty_schema_before_ddl(built: _Built) -> None:
    migration = owned.load_baseline()
    engine = sa.create_engine(built.baseline.sync_url, poolclass=sa.pool.NullPool)
    try:
        with engine.connect() as connection:
            with pytest.raises(
                sa.exc.DBAPIError, match="requires an empty application schema"
            ) as failure:
                with connection.begin():
                    with Operations.context(MigrationContext.configure(connection)):
                        migration.upgrade()
            assert getattr(failure.value.orig, "sqlstate", None) == "55000"
    finally:
        engine.dispose()
    after = _capture(built.baseline)
    assert after.version == built.baseline_capture.version == (BASELINE_REVISION,)
    assert after.catalog == built.baseline_capture.catalog
    assert _schema_statements(after.dump) == _schema_statements(
        built.baseline_capture.dump
    )


def test_baseline_refuses_populated_pgx_namespace(built: _Built) -> None:
    server = built.baseline.server
    server._lease.verify(server)
    with owned._owned_scratch_database(
        server.url.render_as_string(hide_password=False)
    ) as scratch_url:
        url = sa.engine.make_url(scratch_url).set(drivername="postgresql+psycopg")
        engine = sa.create_engine(url, poolclass=sa.pool.NullPool)
        try:
            migration = owned.load_baseline()
            with engine.begin() as connection:
                connection.exec_driver_sql("CREATE SCHEMA pgx")
                connection.exec_driver_sql("CREATE TABLE pgx.retained (id integer)")
                with pytest.raises(
                    sa.exc.DBAPIError, match="requires an empty application schema"
                ) as failure:
                    with connection.begin_nested():
                        with Operations.context(MigrationContext.configure(connection)):
                            migration.upgrade()
                assert getattr(failure.value.orig, "sqlstate", None) == "55000"
                assert connection.scalar(sa.text("SELECT to_regclass('pgx.retained')"))
                assert (
                    connection.scalar(sa.text("SELECT to_regclass('public.users')"))
                    is None
                )
        finally:
            engine.dispose()
