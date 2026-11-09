"""Independent BE-02 default contracts for the fresh MVP baseline.

Expected scalar values come from ADR-036 and the reviewed DEFAULT_SPECS at
pre-squash commit 3ff5375fba01b6ff6f2bc18aaf2d6b2ba18e19c9, not the
baseline's statement constants. Canonical declarations include PostgreSQL's
quoted floating-point zero. Retained tables remain physical schema owners.
The bounded recorder observes emitted DDL; it does not execute PostgreSQL.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import NamedTuple

from tests.fixtures.baseline_migration import (
    assert_baseline_operation_kinds,
    assert_exact_statements,
    table_statements,
)


class ScalarDefault(NamedTuple):
    qualified: str
    family: str
    value: bool | int | float | str
    declaration: str


SCALAR_DEFAULTS = (
    ScalarDefault(
        "dead_letter_jobs.max_retries",
        "integer",
        3,
        "max_retries integer DEFAULT 3 NOT NULL",
    ),
    ScalarDefault(
        "dead_letter_jobs.retry_count",
        "integer",
        0,
        "retry_count integer DEFAULT 0 NOT NULL",
    ),
    ScalarDefault(
        "dead_letter_jobs.status",
        "text",
        "pending",
        "status character varying(20) DEFAULT 'pending'::character varying NOT NULL",
    ),
    ScalarDefault(
        "events.is_active",
        "boolean",
        True,
        "is_active boolean DEFAULT true NOT NULL",
    ),
    ScalarDefault(
        "failed_outbox_events.retry_count",
        "integer",
        0,
        "retry_count integer DEFAULT 0 NOT NULL",
    ),
    ScalarDefault(
        "grades.assessment_type",
        "text",
        "exam",
        "assessment_type character varying(50) DEFAULT 'exam'::character varying "
        "NOT NULL",
    ),
    ScalarDefault(
        "messages.read_status",
        "boolean",
        False,
        "read_status boolean DEFAULT false NOT NULL",
    ),
    ScalarDefault(
        "notification_deliveries.channel",
        "text",
        "inapp",
        "channel character varying DEFAULT 'inapp'::character varying NOT NULL",
    ),
    ScalarDefault(
        "notification_deliveries.status",
        "text",
        "delivered",
        "status character varying DEFAULT 'delivered'::character varying NOT NULL",
    ),
    ScalarDefault(
        "notifications.read",
        "boolean",
        False,
        "read boolean DEFAULT false NOT NULL",
    ),
    ScalarDefault(
        "schedule.parity",
        "text",
        "both",
        "parity character varying DEFAULT 'both'::character varying NOT NULL",
    ),
    ScalarDefault(
        "spotify_integrations.is_connected",
        "boolean",
        False,
        "is_connected boolean DEFAULT false NOT NULL",
    ),
    ScalarDefault(
        "spotify_integrations.is_playing",
        "boolean",
        False,
        "is_playing boolean DEFAULT false NOT NULL",
    ),
    ScalarDefault(
        "stored_events.error_count",
        "integer",
        0,
        "error_count integer DEFAULT 0 NOT NULL",
    ),
    ScalarDefault(
        "stored_events.status",
        "text",
        "pending",
        "status character varying(20) DEFAULT 'pending'::character varying NOT NULL",
    ),
    ScalarDefault(
        "stored_events.version",
        "integer",
        1,
        "version integer DEFAULT 1 NOT NULL",
    ),
    ScalarDefault(
        "user_preferences.dnd_enabled",
        "boolean",
        False,
        "dnd_enabled boolean DEFAULT false NOT NULL",
    ),
    ScalarDefault(
        "user_stats.attendance_percent",
        "float",
        0.0,
        "attendance_percent double precision DEFAULT '0'::double precision NOT NULL",
    ),
    ScalarDefault(
        "user_stats.attendance_present",
        "integer",
        0,
        "attendance_present integer DEFAULT 0 NOT NULL",
    ),
    ScalarDefault(
        "user_stats.attendance_total",
        "integer",
        0,
        "attendance_total integer DEFAULT 0 NOT NULL",
    ),
    ScalarDefault(
        "user_stats.attendance_trend",
        "float",
        0.0,
        "attendance_trend double precision DEFAULT '0'::double precision NOT NULL",
    ),
    ScalarDefault(
        "user_stats.grades_average",
        "float",
        0.0,
        "grades_average double precision DEFAULT '0'::double precision NOT NULL",
    ),
    ScalarDefault(
        "user_stats.grades_trend",
        "float",
        0.0,
        "grades_trend double precision DEFAULT '0'::double precision NOT NULL",
    ),
    ScalarDefault(
        "user_stats.participation_events",
        "integer",
        0,
        "participation_events integer DEFAULT 0 NOT NULL",
    ),
    ScalarDefault(
        "user_stats.participation_groups",
        "integer",
        0,
        "participation_groups integer DEFAULT 0 NOT NULL",
    ),
    ScalarDefault(
        "user_stats.participation_hours",
        "float",
        0.0,
        "participation_hours double precision DEFAULT '0'::double precision NOT NULL",
    ),
    ScalarDefault(
        "user_stats.participation_trend",
        "integer",
        0,
        "participation_trend integer DEFAULT 0 NOT NULL",
    ),
    ScalarDefault(
        "vector_chunks.chunk_index",
        "integer",
        0,
        "chunk_index integer DEFAULT 0 NOT NULL",
    ),
    ScalarDefault(
        "vector_chunks.is_active",
        "boolean",
        True,
        "is_active boolean DEFAULT true NOT NULL",
    ),
)

# Same eleven timestamp candidates as ADR-036; role uses the PostgreSQL enum,
# while the model's server default deliberately remains SQLite-compatible.
SEMANTIC_DEFAULTS = {
    "attachments.created_at": (
        "created_at timestamp with time zone DEFAULT now() NOT NULL"
    ),
    "chats.created_at": "created_at timestamp with time zone DEFAULT now() NOT NULL",
    "chats.updated_at": "updated_at timestamp with time zone DEFAULT now() NOT NULL",
    "dead_letter_jobs.created_at": (
        "created_at timestamp with time zone DEFAULT now() NOT NULL"
    ),
    "dead_letter_jobs.updated_at": (
        "updated_at timestamp with time zone DEFAULT now() NOT NULL"
    ),
    "failed_outbox_events.failed_at": (
        "failed_at timestamp with time zone DEFAULT now() NOT NULL"
    ),
    "grades.created_at": "created_at timestamp with time zone DEFAULT now() NOT NULL",
    "grades.updated_at": "updated_at timestamp with time zone DEFAULT now() NOT NULL",
    "message_reactions.created_at": (
        "created_at timestamp with time zone DEFAULT now() NOT NULL"
    ),
    "messages.created_at": "created_at timestamp with time zone DEFAULT now() NOT NULL",
    "stored_events.created_at": (
        "created_at timestamp with time zone DEFAULT now() NOT NULL"
    ),
    "users.role": "role public.userrole DEFAULT 'student'::public.userrole NOT NULL",
}

# The pre-squash schema's reviewed references to these columns, plus ADR-051's
# restored hot-path indexes. These are a finite allowlist, not a SQL normalizer.
# Other columns, unrelated tables and the complete index policy are outside
# this default-specific assertion.
_COLUMN_REFERENCES = (
    (
        "CREATE INDEX ix_dead_letter_jobs_status ON public.dead_letter_jobs USING "
        "btree (status)"
    ),
    (
        "CREATE INDEX ix_dlq_status_next_retry ON public.dead_letter_jobs USING "
        "btree (status, next_retry_at)"
    ),
    "CREATE INDEX ix_events_is_active ON public.events USING btree (is_active)",
    (
        "CREATE INDEX ix_events_starts_at_is_active ON public.events USING btree "
        "(starts_at, is_active)"
    ),
    (
        "CREATE INDEX ix_failed_outbox_events_failed_at ON "
        "public.failed_outbox_events USING btree (failed_at)"
    ),
    (
        "CREATE INDEX idx_messages_chat_pagination_covering ON public.messages "
        "USING btree (chat_id, created_at DESC, id DESC) INCLUDE (sender_id, "
        "read_status)"
    ),
    (
        "CREATE INDEX ix_messages_unread_chat_sender ON public.messages USING "
        "btree (chat_id, sender_id) WHERE (read_status = false)"
    ),
    (
        "CREATE INDEX idx_messages_chat_created ON public.messages USING btree "
        "(chat_id, created_at DESC)"
    ),
    (
        "CREATE INDEX ix_notification_deliveries_channel ON ONLY "
        "public.notification_deliveries USING btree (channel)"
    ),
    (
        "CREATE INDEX ix_notification_deliveries_dedup ON ONLY "
        "public.notification_deliveries USING btree (notification_id, channel, "
        "subscription_id)"
    ),
    (
        "CREATE INDEX ix_notification_deliveries_notif_channel ON ONLY "
        "public.notification_deliveries USING btree (notification_id, channel)"
    ),
    (
        "CREATE INDEX ix_notification_deliveries_status ON ONLY "
        "public.notification_deliveries USING btree (status)"
    ),
    (
        "CREATE INDEX ix_notifications_read ON ONLY public.notifications USING "
        "btree (read)"
    ),
    (
        "CREATE INDEX ix_notifications_user_id_read ON ONLY public.notifications "
        "USING btree (user_id, read)"
    ),
    (
        "CREATE INDEX idx_notifications_user_unread_created ON ONLY "
        "public.notifications USING btree (user_id, created_at DESC) WHERE (read "
        "= false)"
    ),
    "CREATE INDEX ix_schedule_parity ON public.schedule USING btree (parity)",
    (
        "CREATE INDEX ix_spotify_integrations_is_connected ON "
        "public.spotify_integrations USING btree (is_connected)"
    ),
    (
        "CREATE INDEX ix_spotify_integrations_is_playing ON "
        "public.spotify_integrations USING btree (is_playing)"
    ),
    (
        "CREATE INDEX ix_stored_events_created_at ON public.stored_events USING "
        "btree (created_at)"
    ),
    (
        "CREATE INDEX ix_stored_events_error_count ON public.stored_events USING "
        "btree (error_count)"
    ),
    (
        "CREATE INDEX ix_stored_events_pending_aggregate_created ON "
        "public.stored_events USING btree (aggregate_id, created_at, id) WHERE "
        "(processed_at IS NULL)"
    ),
    (
        "CREATE INDEX ix_stored_events_pending_created ON public.stored_events "
        "USING btree (created_at, id) WHERE (processed_at IS NULL)"
    ),
    "CREATE INDEX ix_stored_events_status ON public.stored_events USING btree (status)",
    (
        "CREATE INDEX ix_stored_events_pending ON public.stored_events USING "
        "btree (status, created_at)"
    ),
    (
        "CREATE INDEX ix_vector_chunks_chunk_index ON public.vector_chunks USING "
        "btree (chunk_index)"
    ),
    (
        "CREATE INDEX ix_vector_chunks_is_active ON public.vector_chunks USING "
        "btree (is_active)"
    ),
    "CREATE INDEX ix_users_role ON public.users USING btree (role)",
)

# 933372f5da9a created the four upper-case labels. Revision 148642dd1207
# appended the five lower-case labels; phase four selected lower-case student.
ROLE_TYPE_SQL = (
    "CREATE TYPE public.userrole AS ENUM (\n"
    "    'STUDENT',\n"
    "    'TEACHER',\n"
    "    'ADMIN',\n"
    "    'SUPERUSER',\n"
    "    'student',\n"
    "    'teacher',\n"
    "    'admin',\n"
    "    'superuser',\n"
    "    'anonymous'\n"
    ")"
)


def assert_default_columns(statements: list[str], expected: Mapping[str, str]) -> None:
    """Check canonical emitted columns and every extra reference to them."""
    assert_baseline_operation_kinds(statements)
    # Unicode-escaped identifiers could hide the table name itself from the
    # bounded selector. They are not part of this canonical baseline format.
    assert not any(
        re.search(r'\bU&\s*"|\bUESCAPE\b', sql, re.ASCII | re.IGNORECASE)
        for sql in statements
    )
    by_table: dict[str, dict[str, str]] = {}
    for qualified, declaration in expected.items():
        table, column = qualified.split(".", 1)
        by_table.setdefault(table, {})[column] = declaration
    for table, columns in by_table.items():
        selected = table_statements(statements, table)
        # Selected canonical statements use unquoted identifiers and single-line
        # standard string literals. Reject unsupported lexical forms instead of
        # allowing comments or quoted payloads to impersonate column references.
        # This bounded admission is not a general SQL parser or normalizer.
        for sql in selected:
            assert all(
                token not in sql for token in ("--", "/*", "*/", "$", "\\", '"')
            ), table
            assert all(line.count("'") % 2 == 0 for line in sql.splitlines()), table
        # Table moves invalidate every column even without a reviewed-column
        # token. Other reviewed-column changes are bounded by exact references.
        assert not any(
            re.search(
                r"\bRENAME\s+TO\b|\bSET\s+SCHEMA\b",
                sql,
                re.ASCII | re.IGNORECASE,
            )
            for sql in selected
            if re.match(r"ALTER\s+TABLE\b", sql, re.ASCII | re.IGNORECASE)
        ), table
        # Match the declared relation, not a PARTITION OF mention of its parent.
        # Keep quoted, unqualified and wrong-schema target spellings visible to
        # the bounded lexical/canonical checks rather than hiding them.
        # A duplicate parent CREATE must remain a duplicate.
        target_create = re.compile(
            r"^CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r'(?:(?:"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_$]*)\s*\.\s*)?'
            rf'"?{re.escape(table)}"?(?![A-Za-z0-9_])',
            re.ASCII | re.IGNORECASE,
        )
        creates = [sql for sql in selected if target_create.match(sql)]
        assert len(creates) == 1, table
        create = creates[0]
        assert create.startswith(f"CREATE TABLE public.{table} ("), table
        for column, declaration in columns.items():
            pattern = re.compile(
                rf"(?<![A-Za-z0-9_]){re.escape(column)}(?![A-Za-z0-9_])",
                re.ASCII | re.IGNORECASE,
            )
            # Include all mentions, not only column-shaped lines: a duplicate,
            # quoted column or extra inline constraint must not hide a change.
            lines = [
                line.strip().removesuffix(",")
                for line in create.splitlines()
                if pattern.search(line)
            ]
            assert lines == [declaration], f"{table}.{column}"
        names = "|".join(re.escape(column) for column in columns)
        references = re.compile(
            rf"(?<![A-Za-z0-9_])(?:{names})(?![A-Za-z0-9_])",
            re.ASCII | re.IGNORECASE,
        )
        assert_exact_statements(
            [sql for sql in selected if references.search(sql)],
            [
                create,
                *[
                    sql
                    for sql in table_statements(_COLUMN_REFERENCES, table)
                    if references.search(sql)
                ],
            ],
        )


def assert_role_type(statements: list[str]) -> None:
    """Bound the native enum and reject extra type/default manipulation."""
    creates = [
        sql for sql in statements if sql.startswith("CREATE TABLE public.users (")
    ]
    assert len(creates) == 1
    assert_exact_statements(
        table_statements(statements, "userrole"),
        [ROLE_TYPE_SQL, creates[0]],
    )


def replace_column(
    statements: list[str], table: str, before: str, after: str
) -> list[str]:
    """Introduce one explicit test defect without changing its expected oracle."""
    changed = list(statements)
    positions = [
        index
        for index, sql in enumerate(changed)
        if sql.startswith(f"CREATE TABLE public.{table} (")
    ]
    assert len(positions) == 1
    position = positions[0]
    assert before != after
    assert changed[position].count(before) == 1
    changed[position] = changed[position].replace(before, after, 1)
    return changed
