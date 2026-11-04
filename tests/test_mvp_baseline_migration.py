"""Unit contract for the squashed MVP baseline revision (Tier 0 migration)."""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import re
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from tests.integration import test_mvp_baseline_schema_equivalence as schema_proof

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = PROJECT_ROOT / "alembic" / "versions" / "202611020000_mvp_baseline.py"


def _load_baseline() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mvp_baseline_under_test", BASELINE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class _Bind:
    def __init__(self, dialect: str, pg_cron_available: bool) -> None:
        self.dialect = type("Dialect", (), {"name": dialect})()
        self._pg_cron_available = pg_cron_available
        self.queries: list[str] = []

    def execute(self, statement: Any) -> _Result:
        sql = str(statement)
        self.queries.append(sql)
        if "pg_available_extensions" in sql and self._pg_cron_available:
            return _Result((1,))
        return _Result(None)


class _Op:
    def __init__(self, bind: _Bind) -> None:
        self._bind = bind
        self.executed: list[str] = []

    def get_bind(self) -> _Bind:
        return self._bind

    def execute(self, statement: str) -> None:
        self.executed.append(statement)


def test_baseline_revision_is_the_root_of_the_squashed_chain() -> None:
    module = _load_baseline()

    assert module.revision == "202611020000"
    assert module.down_revision is None
    assert module.branch_labels is None
    assert module.depends_on is None


def test_downgrade_is_irreversible_and_refuses_before_changing_schema() -> None:
    module = _load_baseline()

    assert module.downgrade_policy == "irreversible"
    with pytest.raises(RuntimeError) as raised:
        module.downgrade()
    assert str(raised.value) == module.downgrade_reason
    assert "consistent backup" in module.downgrade_reason


def test_upgrade_requires_postgresql_and_executes_nothing_elsewhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_baseline()
    op = _Op(_Bind("sqlite", pg_cron_available=False))
    monkeypatch.setattr(module, "op", op)

    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        module.upgrade()
    assert op.executed == []


def test_upgrade_omits_the_redundant_attempt_keyed_delivery_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUD-272: the attempt-timestamp UNIQUE is absent; the claim ledger is the guard."""
    module = _load_baseline()
    op = _Op(_Bind("postgresql", pg_cron_available=False))
    monkeypatch.setattr(module, "op", op)

    module.upgrade()

    executed = "\n".join(op.executed)
    assert "ADD CONSTRAINT uq_notification_delivery_once UNIQUE" not in executed
    assert "public.uq_notification_delivery_once ATTACH PARTITION" not in executed
    assert "uq_notification_delivery_once_claim UNIQUE NULLS NOT DISTINCT" in executed
    assert not any(
        "public.notification_deliveries" in s and " UNIQUE " in s for s in op.executed
    )


def test_upgrade_creates_the_restored_and_delivery_once_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_baseline()
    op = _Op(_Bind("postgresql", pg_cron_available=False))
    monkeypatch.setattr(module, "op", op)

    module.upgrade()

    executed = "\n".join(op.executed)
    assert "CREATE ROLE ue_rls_bypass NOLOGIN" in executed
    assert "CREATE TABLE public.notification_delivery_once" in executed
    assert "uq_notification_delivery_once_claim UNIQUE NULLS NOT DISTINCT" in executed
    for index_name in (
        "ux_users_lower_email",
        "ix_user_profiles_full_name_lower",
        "ix_user_profiles_full_name_trgm",
        "idx_notifications_user_unread_created",
        "idx_messages_chat_created",
        "ix_stored_events_pending",
        "idx_active_sessions_user_valid",
        "ix_active_sessions_user_active_created",
    ):
        assert index_name in executed, index_name
    partitions = [s for s in op.executed if "PARTITION OF" in s]
    assert len(partitions) == 4 * 26
    assert not any("cron.schedule" in s for s in op.executed)


def test_upgrade_schedules_pg_cron_jobs_only_when_the_extension_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_baseline()
    op = _Op(_Bind("postgresql", pg_cron_available=True))
    monkeypatch.setattr(module, "op", op)

    module.upgrade()

    assert op.executed[-4:] == list(module._PG_CRON_STATEMENTS)
    assert op.executed[-4] == "CREATE EXTENSION IF NOT EXISTS pg_cron"
    assert sum("cron.schedule" in s for s in op.executed) == 3


# Independent inventory of the fifty named keys carried by the pre-refactor
# baseline. The runtime CREATE statements must preserve names and ordered columns.
_EXPECTED_INLINE_PRIMARY_KEYS = {
    "active_sessions": ("active_sessions_pkey", "id"),
    "attachments": ("attachments_pkey", "id"),
    "chat_participants": ("chat_participants_pkey", "chat_id, user_id"),
    "chat_read_receipts": ("chat_read_receipts_pkey", "id"),
    "chat_send_receipts": ("chat_send_receipts_pkey", "id"),
    "chats": ("chats_pkey", "id"),
    "cwv_observations": ("cwv_observations_pkey", "id"),
    "data_access_logs": ("data_access_logs_pkey", "id, created_at"),
    "dead_letter_jobs": ("dead_letter_jobs_pkey", "id"),
    "email_change_tokens": ("email_change_tokens_pkey", "id"),
    "event_attendance": ("event_attendance_pkey", "id"),
    "event_files": ("event_files_pkey", "id"),
    "events": ("events_pkey", "id"),
    "failed_login_attempts": ("failed_login_attempts_pkey", "id, attempted_at"),
    "failed_outbox_events": ("failed_outbox_events_pkey", "id"),
    "grades": ("grades_pkey", "id"),
    "groups": ("groups_pkey", "id"),
    "invite_codes": ("invite_codes_pkey", "id"),
    "login_history": ("login_history_pkey", "id"),
    "message_reactions": ("message_reactions_pkey", "id"),
    "messages": ("messages_pkey", "id"),
    "mfa_challenges": ("mfa_challenges_pkey", "id"),
    "mfa_email_deliveries": ("mfa_email_deliveries_pkey", "id"),
    "mfa_totp_enrollments": ("mfa_totp_enrollments_pkey", "id"),
    "news_comments": ("news_comments_pkey", "id"),
    "news_likes": ("news_likes_pkey", "id"),
    "news_media_assets": ("news_media_assets_pkey", "id"),
    "news": ("news_pkey", "id"),
    "notification_deliveries": ("notification_deliveries_pkey", "id, attempted_at"),
    "notification_queue_jobs": ("notification_queue_jobs_pkey", "id"),
    "notifications": ("notifications_pkey", "id, created_at"),
    "password_reset_tokens": ("password_reset_tokens_pkey", "id"),
    "push_subscriptions": ("push_subscriptions_pkey", "id"),
    "quarantine_reservations": ("quarantine_reservations_pkey", "id"),
    "quarantine_storage_scopes": ("quarantine_storage_scopes_pkey", "scope_id"),
    "recovery_codes": ("recovery_codes_pkey", "id"),
    "schedule": ("schedule_pkey", "id"),
    "spotify_integrations": ("spotify_integrations_pkey", "user_id"),
    "stored_events": ("stored_events_pkey", "id"),
    "stories": ("stories_pkey", "id"),
    "tenants": ("tenants_pkey", "id"),
    "trusted_devices": ("trusted_devices_pkey", "id"),
    "user_education_paths": ("user_education_paths_pkey", "user_id"),
    "user_preferences": ("user_preferences_pkey", "user_id"),
    "user_profiles": ("user_profile_details_pkey", "user_id"),
    "user_push_topics": ("user_push_topics_pkey", "user_id"),
    "user_stats": ("user_stats_pkey", "user_id"),
    "users": ("users_pkey", "id"),
    "vector_chunks": ("vector_chunks_pkey", "id"),
    "notification_delivery_once": ("notification_delivery_once_pkey", "id"),
}


def _assert_inline_primary_keys(statements: list[str]) -> None:
    found: dict[str, tuple[str, str]] = {}
    for statement in statements:
        assert not re.search(r"ALTER TABLE.*PRIMARY KEY", statement, re.DOTALL)
        table = re.match(r"CREATE TABLE public\.(\w+) \(", statement)
        keys = re.findall(r"CONSTRAINT (\w+) PRIMARY KEY \(([^)]+)\)", statement)
        if not keys:
            continue
        assert table is not None
        assert len(keys) == 1
        assert table[1] not in found
        found[table[1]] = keys[0]
    assert found == _EXPECTED_INLINE_PRIMARY_KEYS


def test_baseline_creates_named_primary_keys_with_their_empty_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_baseline()
    op = _Op(_Bind("postgresql", pg_cron_available=False))
    monkeypatch.setattr(module, "op", op)
    module.upgrade()
    _assert_inline_primary_keys(op.executed)


@pytest.mark.parametrize(
    "mutation", ["missing", "name", "columns", "deferred", "duplicate"]
)
def test_inline_primary_key_contract_rejects_schema_and_timing_drift(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    module = _load_baseline()
    op = _Op(_Bind("postgresql", pg_cron_available=False))
    monkeypatch.setattr(module, "op", op)
    module.upgrade()
    statements = list(op.executed)
    index = next(
        i
        for i, statement in enumerate(statements)
        if statement.startswith("CREATE TABLE public.data_access_logs (")
    )
    key = "CONSTRAINT data_access_logs_pkey PRIMARY KEY (id, created_at)"
    assert statements[index].count(key) == 1
    if mutation in {"missing", "deferred"}:
        statements[index] = statements[index].replace(",\n    " + key, "")
        if mutation == "deferred":
            statements.append("ALTER TABLE ONLY public.data_access_logs ADD " + key)
    elif mutation == "name":
        statements[index] = statements[index].replace(
            key, key.replace("_pkey", "_wrong")
        )
    elif mutation == "columns":
        statements[index] = statements[index].replace(
            "PRIMARY KEY (id, created_at)", "PRIMARY KEY (created_at, id)"
        )
    else:
        statements.append(statements[index])
    with pytest.raises(AssertionError):
        _assert_inline_primary_keys(statements)


# These controls exercise the real proof functions with synthetic dump/catalog
# inputs. They do not start containers, execute DDL, or replace the comparator.
# The approved additions are independently enumerated, not derived from the
# implementation's broad matching expression or the baseline revision constants.
_PROOF_RETAINED_STATEMENT = "CREATE TABLE public.retained_control (id integer)"
_PROOF_REMOVED_INDEX = (
    "CREATE UNIQUE INDEX ix_users_email_lower ON public.users USING btree "
    "(lower((email)::text))"
)
# Owner decision, 2026-11-03: the one audited replacement of the
# messages_participant_isolation policy (NULLIF form), recorded independently of the
# equivalence module. The pre-squash form is removed and the NULLIF form is added.
_PROOF_MESSAGES_QUAL_BEFORE = (
    "(chat_id IN ( SELECT chat_participants.chat_id\n   FROM chat_participants\n"
    "  WHERE (chat_participants.user_id = "
    "(current_setting('app.current_user_id'::text, true))::uuid)))"
)
_PROOF_MESSAGES_QUAL_AFTER = (
    "(chat_id IN ( SELECT chat_participants.chat_id\n   FROM chat_participants\n"
    "  WHERE (chat_participants.user_id = "
    "(NULLIF(current_setting('app.current_user_id'::text, true), ''::text))::uuid)))"
)
_PROOF_MESSAGES_STATEMENT_BEFORE = (
    "CREATE POLICY messages_participant_isolation ON public.messages USING "
    "((chat_id IN ( SELECT chat_participants.chat_id FROM public.chat_participants "
    "WHERE (chat_participants.user_id = "
    "(current_setting('app.current_user_id'::text, true))::uuid))))"
)
_PROOF_MESSAGES_STATEMENT_AFTER = (
    "CREATE POLICY messages_participant_isolation ON public.messages USING "
    "((chat_id IN ( SELECT chat_participants.chat_id FROM public.chat_participants "
    "WHERE (chat_participants.user_id = "
    "(NULLIF(current_setting('app.current_user_id'::text, true), ''::text))::uuid))))"
)
_PROOF_MESSAGES_ROW_BEFORE = repr(
    (
        "messages",
        "messages_participant_isolation",
        "PERMISSIVE",
        "{public}",
        "ALL",
        _PROOF_MESSAGES_QUAL_BEFORE,
        None,
    )
)
_PROOF_MESSAGES_ROW_AFTER = repr(
    (
        "messages",
        "messages_participant_isolation",
        "PERMISSIVE",
        "{public}",
        "ALL",
        _PROOF_MESSAGES_QUAL_AFTER,
        None,
    )
)
_PROOF_PARENT_INDEXES = (
    (
        "CREATE UNIQUE INDEX ux_users_lower_email ON public.users USING btree "
        "(lower((email)::text))"
    ),
    (
        "CREATE INDEX ix_user_profiles_full_name_lower ON public.user_profiles "
        "USING btree (lower((full_name)::text) text_pattern_ops) "
        "WHERE (full_name IS NOT NULL)"
    ),
    (
        "CREATE INDEX ix_user_profiles_full_name_trgm ON public.user_profiles "
        "USING gin (full_name public.gin_trgm_ops) WHERE (full_name IS NOT NULL)"
    ),
    (
        "CREATE INDEX idx_notifications_user_unread_created ON ONLY "
        "public.notifications USING btree (user_id, created_at DESC) "
        "WHERE (read = false)"
    ),
    (
        "CREATE INDEX idx_messages_chat_created ON public.messages USING btree "
        "(chat_id, created_at DESC)"
    ),
    (
        "CREATE INDEX ix_stored_events_pending ON public.stored_events "
        "USING btree (status, created_at)"
    ),
    (
        "CREATE INDEX idx_active_sessions_user_valid ON public.active_sessions "
        "USING btree (user_id, revoked_at) WHERE (revoked_at IS NULL)"
    ),
    (
        "CREATE INDEX ix_active_sessions_user_active_created "
        "ON public.active_sessions USING btree (user_id, created_at) "
        "WHERE (revoked_at IS NULL)"
    ),
)
_PROOF_CLAIM_STATEMENTS = (
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
_PROOF_PARTITION_SUFFIXES = (
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

# Owner decision, 2026-11-04 (AUD-272), recorded independently of the equivalence module:
# the redundant attempt-keyed UNIQUE on notification_deliveries and its 26 partition
# constraints and attachments disappear from the pre-squash side of the proof.
_PROOF_DELIVERY_ONCE_REMOVED_PARTITIONS = (
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
_PROOF_DELIVERY_ONCE_REMOVED_STATEMENTS = (
    "ALTER TABLE ONLY public.notification_deliveries\n"
    "    ADD CONSTRAINT uq_notification_delivery_once UNIQUE (notification_id, "
    "channel, subscription_id, attempted_at)",
    *(
        statement
        for suffix, child in _PROOF_DELIVERY_ONCE_REMOVED_PARTITIONS
        for statement in (
            f"ALTER TABLE ONLY public.notification_deliveries_{suffix}\n"
            f"    ADD CONSTRAINT {child} UNIQUE (notification_id, channel, "
            "subscription_id, attempted_at)",
            "ALTER INDEX public.uq_notification_delivery_once ATTACH PARTITION "
            f"public.{child}",
        )
    ),
)
_PROOF_DELIVERY_ONCE_REMOVED_ROWS = tuple(
    repr((child, "uq_notification_delivery_once", None))
    for _suffix, child in _PROOF_DELIVERY_ONCE_REMOVED_PARTITIONS
)


def _proof_statement_inputs() -> tuple[list[str], list[str]]:
    additions = [*_PROOF_CLAIM_STATEMENTS, *_PROOF_PARENT_INDEXES]
    for suffix in _PROOF_PARTITION_SUFFIXES:
        table = f"notifications_{suffix}"
        child = f"{table}_user_id_created_at_idx1"
        additions.extend(
            (
                (
                    f"CREATE INDEX {child} ON public.{table} USING btree "
                    "(user_id, created_at DESC) WHERE (read = false)"
                ),
                (
                    "ALTER INDEX public.idx_notifications_user_unread_created "
                    f"ATTACH PARTITION public.{child}"
                ),
            )
        )
    assert len(additions) == len(set(additions)) == 63
    before = [
        _PROOF_RETAINED_STATEMENT,
        _PROOF_REMOVED_INDEX,
        _PROOF_MESSAGES_STATEMENT_BEFORE,
        *_PROOF_DELIVERY_ONCE_REMOVED_STATEMENTS,
    ]
    after = [
        _PROOF_RETAINED_STATEMENT,
        *additions,
        _PROOF_MESSAGES_STATEMENT_AFTER,
    ]
    return before, after


def _run_statement_proof(
    monkeypatch: pytest.MonkeyPatch, before: list[str], after: list[str]
) -> None:
    built = SimpleNamespace(
        pre_squash_capture=schema_proof._Captured(";\n".join(before) + ";", (), ()),
        baseline_capture=schema_proof._Captured(";\n".join(after) + ";", (), ()),
    )

    def reject_recapture(database: object) -> str:
        pytest.fail("statement comparison must use already captured evidence")

    monkeypatch.setattr(schema_proof, "_dump", reject_recapture)
    schema_proof.test_statement_level_schema_differs_only_by_the_audited_additions(
        built
    )


def _replace_proof_statement(
    statements: list[str], before: str, after: str
) -> list[str]:
    assert before != after
    assert sum(statement.count(before) for statement in statements) == 1
    changed = [statement.replace(before, after) for statement in statements]
    assert len(changed) == len(statements)
    assert changed != statements
    return changed


def test_schema_statement_proof_accepts_the_exact_finite_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before, after = _proof_statement_inputs()
    _run_statement_proof(monkeypatch, before, after)


@pytest.mark.parametrize(
    ("defect", "side", "before", "after"),
    [
        (
            "replacement-not-unique",
            "after",
            "CREATE UNIQUE INDEX ux_users_lower_email",
            "CREATE INDEX ux_users_lower_email",
        ),
        (
            "replacement-wrong-key",
            "after",
            _PROOF_PARENT_INDEXES[0],
            _PROOF_PARENT_INDEXES[0].replace("lower((email)::text)", "email"),
        ),
        (
            "missing-pattern-opclass",
            "after",
            "lower((full_name)::text) text_pattern_ops",
            "lower((full_name)::text)",
        ),
        (
            "wrong-trigram-method",
            "after",
            "USING gin (full_name public.gin_trgm_ops)",
            "USING btree (full_name public.gin_trgm_ops)",
        ),
        (
            "missing-profile-predicate",
            "after",
            _PROOF_PARENT_INDEXES[1],
            _PROOF_PARENT_INDEXES[1].replace(" WHERE (full_name IS NOT NULL)", ""),
        ),
        (
            "wrong-notification-order",
            "after",
            _PROOF_PARENT_INDEXES[3],
            _PROOF_PARENT_INDEXES[3].replace("created_at DESC", "created_at"),
        ),
        (
            "wrong-notification-predicate",
            "after",
            _PROOF_PARENT_INDEXES[3],
            _PROOF_PARENT_INDEXES[3].replace("read = false", "read = true"),
        ),
        (
            "wrong-message-key",
            "after",
            "(chat_id, created_at DESC)",
            "(sender_id, created_at DESC)",
        ),
        (
            "wrong-pending-table",
            "after",
            _PROOF_PARENT_INDEXES[5],
            _PROOF_PARENT_INDEXES[5].replace(
                "ON public.stored_events", "ON public.users"
            ),
        ),
        (
            "wrong-session-predicate",
            "after",
            _PROOF_PARENT_INDEXES[6],
            _PROOF_PARENT_INDEXES[6].replace(
                "revoked_at IS NULL", "revoked_at IS NOT NULL"
            ),
        ),
        (
            "claim-subscription-not-null",
            "after",
            "    subscription_id uuid,",
            "    subscription_id uuid NOT NULL,",
        ),
        (
            "claim-channel-bound",
            "after",
            "    channel character varying(50) NOT NULL,",
            "    channel character varying(51) NOT NULL,",
        ),
        (
            "claim-nulls-distinct",
            "after",
            "UNIQUE NULLS NOT DISTINCT",
            "UNIQUE",
        ),
        (
            "wrong-partition-attachment",
            "after",
            ("ATTACH PARTITION public.notifications_2026_05_user_id_created_at_idx1"),
            "ATTACH PARTITION public.unrelated_index",
        ),
        (
            "allowed-name-in-unrelated-comment",
            "after",
            _PROOF_CLAIM_STATEMENTS[0],
            (
                "COMMENT ON TABLE public.retained_control IS "
                "'notification_delivery_once'"
            ),
        ),
        (
            "wrong-removed-definition",
            "before",
            _PROOF_REMOVED_INDEX,
            _PROOF_REMOVED_INDEX.replace("lower((email)::text)", "email"),
        ),
    ],
    ids=[
        "replacement-not-unique",
        "replacement-wrong-key",
        "missing-pattern-opclass",
        "wrong-trigram-method",
        "missing-profile-predicate",
        "wrong-notification-order",
        "wrong-notification-predicate",
        "wrong-message-key",
        "wrong-pending-table",
        "wrong-session-predicate",
        "claim-subscription-not-null",
        "claim-channel-bound",
        "claim-nulls-distinct",
        "wrong-partition-attachment",
        "allowed-name-in-unrelated-comment",
        "wrong-removed-definition",
    ],
)
def test_schema_statement_proof_rejects_shape_drift_with_the_same_counts(
    monkeypatch: pytest.MonkeyPatch,
    defect: str,
    side: str,
    before: str,
    after: str,
) -> None:
    original, baseline = _proof_statement_inputs()
    _run_statement_proof(monkeypatch, original, baseline)
    changed = _replace_proof_statement(
        original if side == "before" else baseline, before, after
    )

    with pytest.raises(AssertionError):
        _run_statement_proof(
            monkeypatch,
            changed if side == "before" else original,
            changed if side == "after" else baseline,
        )


def _proof_catalog_inputs() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    before: dict[str, list[str]] = {name: [] for name in schema_proof.CATALOG_PROBES}
    before["relations"] = [repr(("users", "r", True, True, False, "p", "d", ""))]
    before["policies"] = [_PROOF_MESSAGES_ROW_BEFORE]
    before["partition_bounds"] = list(_PROOF_DELIVERY_ONCE_REMOVED_ROWS)
    after = deepcopy(before)
    after["policies"] = [_PROOF_MESSAGES_ROW_AFTER]
    after["relations"].append(
        repr(("notification_delivery_once", "r", False, False, False, "p", "d", ""))
    )
    fields = (
        ("id", None, "NO", "uuid", None),
        ("notification_id", None, "NO", "uuid", None),
        ("subscription_id", None, "YES", "uuid", None),
        ("channel", None, "NO", "character varying", 50),
        ("created_at", "now()", "NO", "timestamp with time zone", None),
    )
    after["columns"] = [
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
        for name, default, nullable, data_type, length in fields
    ]
    # Index inheritance is present in pg_inherits without a table partition bound.
    after["partition_bounds"] = [
        repr(
            (
                f"notifications_{suffix}_user_id_created_at_idx1",
                "idx_notifications_user_unread_created",
                None,
            )
        )
        for suffix in _PROOF_PARTITION_SUFFIXES
    ]
    assert len(after["partition_bounds"]) == 26
    assert len(set(after["partition_bounds"])) == 26
    for rows in after.values():
        rows.sort()
    return before, after


def _run_catalog_proof(
    monkeypatch: pytest.MonkeyPatch,
    before: dict[str, list[str]],
    after: dict[str, list[str]],
) -> None:
    built = SimpleNamespace(
        pre_squash_capture=schema_proof._Captured(
            "", tuple((name, tuple(rows)) for name, rows in before.items()), ()
        ),
        baseline_capture=schema_proof._Captured(
            "", tuple((name, tuple(rows)) for name, rows in after.items()), ()
        ),
    )

    def reject_recapture(database: object) -> dict[str, list[str]]:
        pytest.fail("catalog comparison must use already captured evidence")

    monkeypatch.setattr(schema_proof, "_probe", reject_recapture)
    schema_proof.test_catalog_facts_outside_the_additions_are_identical(built)


def test_schema_catalog_proof_accepts_unchanged_facts_and_exact_claim_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before, after = _proof_catalog_inputs()
    _run_catalog_proof(monkeypatch, before, after)


@pytest.mark.parametrize(
    ("group", "identity", "position", "replacement"),
    [
        ("relations", "notification_delivery_once", 1, "p"),
        ("relations", "notification_delivery_once", 2, True),
        ("relations", "notification_delivery_once", 7, "{fillfactor=70}"),
        ("columns", "id", 4, "text"),
        ("columns", "notification_id", 3, "YES"),
        ("columns", "subscription_id", 3, "NO"),
        ("columns", "channel", 5, 51),
        ("columns", "created_at", 2, None),
    ],
)
def test_schema_catalog_proof_rejects_drift_inside_an_approved_object(
    monkeypatch: pytest.MonkeyPatch,
    group: str,
    identity: str,
    position: int,
    replacement: object,
) -> None:
    before, after = _proof_catalog_inputs()
    _run_catalog_proof(monkeypatch, before, after)
    changed = deepcopy(after)
    matches = 0
    for index, rendered in enumerate(changed[group]):
        row = list(ast.literal_eval(rendered))
        key = row[0] if group == "relations" else row[1]
        if key == identity:
            assert row[position] != replacement
            row[position] = replacement
            changed[group][index] = repr(tuple(row))
            matches += 1
    assert matches == 1
    changed[group].sort()
    assert changed != after

    with pytest.raises(AssertionError):
        _run_catalog_proof(monkeypatch, before, changed)


def test_schema_statement_proof_still_rejects_unapproved_removed_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before, after = _proof_statement_inputs()
    _run_statement_proof(monkeypatch, before, after)
    changed = [item for item in after if item != _PROOF_RETAINED_STATEMENT]
    assert len(changed) == len(after) - 1

    with pytest.raises(AssertionError):
        _run_statement_proof(monkeypatch, before, changed)


def test_schema_catalog_proof_still_rejects_unapproved_relation_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before, after = _proof_catalog_inputs()
    _run_catalog_proof(monkeypatch, before, after)
    changed = deepcopy(after)
    changed["relations"].remove(before["relations"][0])
    changed["relations"].append(repr(("users", "v", True, True, False, "p", "d", "")))
    changed["relations"].sort()

    with pytest.raises(AssertionError):
        _run_catalog_proof(monkeypatch, before, changed)


@pytest.mark.parametrize(
    "inherited",
    ["DATABASE_URL_FILE", "database_url", "ENV_FILE_PATH"],
)
def test_schema_proof_child_keeps_the_owned_database_url_authoritative(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, inherited: str
) -> None:
    owned_url = "postgresql+asyncpg://127.0.0.1:5432/owned_schema_proof"
    value = (
        "postgresql+asyncpg://127.0.0.1:1/not_the_owned_database"
        if inherited == "database_url"
        else str(tmp_path / "must-not-be-read")
    )
    monkeypatch.setenv(inherited, value)
    captured: list[tuple[list[str], Path, dict[str, object]]] = []

    async def capture(
        argv: list[str], cwd: Path, env: dict[str, str] | None = None
    ) -> tuple[int, bytes, bytes]:
        assert env is not None
        captured.append(
            (
                argv,
                cwd,
                {
                    "owned_url": env.get("DATABASE_URL") == owned_url,
                    "url_names": tuple(
                        name for name in env if name.casefold() == "database_url"
                    ),
                    "file_present": any(
                        name.casefold() == "database_url_file" for name in env
                    ),
                    "dotenv_disabled": env.get("ENV_FILE_PATH") == "",
                },
            )
        )
        return 0, b"controlled-output", b""

    monkeypatch.setattr(schema_proof, "_run_fixed_argv", capture)

    completed = schema_proof._alembic(tmp_path, owned_url, "check")

    assert completed.returncode == 0
    assert completed.stdout == "controlled-output"
    assert completed.stderr == ""
    assert len(captured) == 1
    argv, cwd, observed = captured[0]
    assert argv == [sys.executable, "-m", "alembic", "check"]
    assert cwd == tmp_path
    assert observed == {
        "owned_url": True,
        "url_names": ("DATABASE_URL",),
        "file_present": False,
        "dotenv_disabled": True,
    }


@pytest.mark.parametrize(
    "outcome",
    [
        0,
        7,
        "timeout",
        "communication-timeout",
        "communication-error",
        "cancel",
        "reap-timeout",
    ],
)
def test_schema_proof_child_is_bounded_and_reaped_without_changing_its_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: int | str
) -> None:
    spawned: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    deadlines: list[float] = []
    failure: BaseException
    if outcome == "communication-error":
        failure = OSError("controlled schema-proof pipe failure")
    elif outcome == "cancel":
        failure = asyncio.CancelledError("controlled schema-proof cancellation")
    else:
        failure = TimeoutError("controlled schema-proof child deadline")

    class Process:
        def __init__(self) -> None:
            self.returncode: int | None = None
            self.killed = False
            self.reaped = False
            self.started = asyncio.Event()
            self.terminated = asyncio.Event()
            self.communication_finished = False
            self.wait_calls = 0
            self.wait_started = asyncio.Event()
            self.wait_cancelled = False

        async def communicate(self) -> tuple[bytes, bytes]:
            self.started.set()
            if outcome in {"communication-timeout", "communication-error"}:
                self.communication_finished = True
                raise failure
            if outcome == "reap-timeout":
                try:
                    await asyncio.Event().wait()
                finally:
                    self.communication_finished = True
            if outcome in {"timeout", "cancel"}:
                await self.terminated.wait()
            self.returncode = -9 if self.killed else int(outcome)
            self.communication_finished = True
            self.reaped = True
            return b"controlled-stdout", b"controlled-stderr"

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9
            self.terminated.set()

        async def wait(self) -> int:
            self.wait_calls += 1
            self.wait_started.set()
            if outcome == "reap-timeout":
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    self.wait_cancelled = True
                    raise
            await self.terminated.wait()
            self.reaped = True
            assert self.returncode is not None
            return self.returncode

    process = Process()

    async def create(*argv: str, **kwargs: Any) -> Process:
        spawned.append((argv, kwargs))
        return process

    async def bounded(awaitable: Any, timeout: float | None) -> Any:
        assert not isinstance(timeout, bool)
        assert isinstance(timeout, (int, float))
        assert 0 < timeout <= 300
        deadlines.append(timeout)
        if len(deadlines) == 1 and outcome in {"timeout", "cancel", "reap-timeout"}:
            await process.started.wait()
            assert not process.communication_finished
            raise failure
        if len(deadlines) == 2 and outcome == "reap-timeout":
            await process.wait_started.wait()
            raise TimeoutError("controlled cleanup deadline")
        return await awaitable

    monkeypatch.setattr(schema_proof.asyncio, "create_subprocess_exec", create)
    monkeypatch.setattr(schema_proof.asyncio, "wait_for", bounded)
    argv = ["controlled-python", "-m", "alembic", "check"]
    operation = schema_proof._run_fixed_argv(argv, tmp_path, {"CONTROL": "1"})

    if isinstance(outcome, str):
        with pytest.raises(type(failure)) as caught:
            asyncio.run(operation)
        assert caught.value is failure
        assert process.killed
        assert process.wait_calls == 1
        if outcome == "reap-timeout":
            assert not process.reaped
            assert process.wait_cancelled
            assert failure.__notes__ == [
                "schema-proof direct-child cleanup exceeded its deadline"
            ]
        else:
            assert process.reaped
    else:
        result = asyncio.run(operation)
        assert result == (outcome, b"controlled-stdout", b"controlled-stderr")
        assert process.reaped
        assert not process.killed

    assert process.communication_finished
    assert len(deadlines) == (2 if isinstance(outcome, str) else 1)
    assert spawned == [
        (
            tuple(argv),
            {
                "cwd": tmp_path,
                "env": {"CONTROL": "1"},
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.PIPE,
            },
        )
    ]


def _catalog_relation(name: str, row_security: bool) -> str:
    return repr((name, "r", row_security, False, False, "p", "d", ""))


def _catalog_policy(
    table: str, name: str, permissive: str, qual: str, check: str | None
) -> str:
    return repr((table, name, permissive, "{public}", "ALL", qual, check))


@pytest.mark.parametrize(
    ("policies", "expected"),
    [
        (
            [_catalog_policy("messages", "allow_all", "PERMISSIVE", "true", None)],
            ["messages.allow_all"],
        ),
        (
            [
                _catalog_policy(
                    "messages", "write_all", "PERMISSIVE", "(user_id = 1)", "(true)"
                )
            ],
            ["messages.write_all"],
        ),
        (
            [
                _catalog_policy(
                    "messages", "restrictive_all", "RESTRICTIVE", "true", None
                ),
                _catalog_policy(
                    "users", "table_without_rls", "PERMISSIVE", "true", None
                ),
                _catalog_policy(
                    "messages",
                    "participant_scope",
                    "PERMISSIVE",
                    "(NULLIF(current_setting('app.current_user_id'::text, true)) IS NOT NULL)",
                    None,
                ),
            ],
            [],
        ),
    ],
)
def test_unconditional_policy_catalog_check_flags_only_permissive_true_on_rls_tables(
    policies: list[str], expected: list[str]
) -> None:
    relations = (_catalog_relation("messages", True), _catalog_relation("users", False))
    rls_tables = schema_proof._rls_table_names(relations)

    assert rls_tables == frozenset({"messages"})
    assert (
        schema_proof._unconditional_permissive_policies(tuple(policies), rls_tables)
        == expected
    )
