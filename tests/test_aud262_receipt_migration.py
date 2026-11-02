"""Executed baseline contracts for private durable chat-send receipts."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from tests.fixtures.baseline_migration import (
    assert_baseline_operation_kinds,
    assert_downgrade_refuses,
    assert_exact_statements,
    bind_baseline,
    capture_baseline,
    normalize_sql,
    table_statements,
)

# Compatibility only: the existing temporary-schema integration fixture imports
# this lazy loader. Its deleted-revision failure remains unresolved; never point
# this caller at the full public-schema baseline.
ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    ROOT / "alembic" / "versions" / "202610250001_add_chat_send_receipts.py"
)


def _load_migration() -> Any:
    assert MIGRATION_PATH.is_file(), "Durable chat-send receipt migration is missing"
    spec = importlib.util.spec_from_file_location(
        "aud262_receipt_migration_contract", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


_EXPECTED_RECEIPT_SQL = (
    (
        "CREATE TABLE public.chat_send_receipts (\n"
        "    id uuid NOT NULL,\n"
        "    chat_id uuid NOT NULL,\n"
        "    user_id uuid NOT NULL,\n"
        "    key_digest character varying(64) NOT NULL,\n"
        "    message_id uuid,\n"
        "    completed_at timestamp with time zone NOT NULL,\n"
        "    expires_at timestamp with time zone NOT NULL\n"
        ")"
    ),
    (
        "ALTER TABLE ONLY public.chat_send_receipts\n"
        "    ADD CONSTRAINT chat_send_receipts_pkey PRIMARY KEY (id)"
    ),
    (
        "ALTER TABLE ONLY public.chat_send_receipts\n"
        "    ADD CONSTRAINT uq_chat_send_receipts_chat_user_key UNIQUE "
        "(chat_id, user_id, key_digest)"
    ),
    (
        "ALTER TABLE ONLY public.chat_send_receipts\n"
        "    ADD CONSTRAINT chat_send_receipts_chat_id_fkey FOREIGN KEY "
        "(chat_id) REFERENCES public.chats(id) ON DELETE CASCADE"
    ),
    (
        "ALTER TABLE ONLY public.chat_send_receipts\n"
        "    ADD CONSTRAINT chat_send_receipts_message_id_fkey FOREIGN KEY "
        "(message_id) REFERENCES public.messages(id) ON DELETE SET NULL"
    ),
    (
        "ALTER TABLE ONLY public.chat_send_receipts\n"
        "    ADD CONSTRAINT chat_send_receipts_user_id_fkey FOREIGN KEY "
        "(user_id) REFERENCES public.users(id) ON DELETE CASCADE"
    ),
    (
        "CREATE INDEX ix_chat_send_receipts_expires_at ON "
        "public.chat_send_receipts USING btree (expires_at, id)"
    ),
    (
        "CREATE INDEX ix_chat_send_receipts_message_id ON "
        "public.chat_send_receipts USING btree (message_id)"
    ),
    (
        "CREATE INDEX ix_chat_send_receipts_user_id ON "
        "public.chat_send_receipts USING btree (user_id)"
    ),
    "ALTER TABLE ONLY public.chat_send_receipts FORCE ROW LEVEL SECURITY",
    "ALTER TABLE public.chat_send_receipts ENABLE ROW LEVEL SECURITY",
    (
        "CREATE POLICY chat_send_receipts_owner_participant ON "
        "public.chat_send_receipts USING (((user_id = "
        "(NULLIF(current_setting('app.current_user_id'::text, true), "
        "''::text))::uuid) AND (EXISTS ( SELECT 1\n"
        "   FROM (public.chat_participants participant\n"
        "     JOIN public.chats chat ON ((chat.id = participant.chat_id)))\n"
        "  WHERE ((participant.chat_id = chat_send_receipts.chat_id) AND "
        "(participant.user_id = chat_send_receipts.user_id)))))) WITH "
        "CHECK (((user_id = "
        "(NULLIF(current_setting('app.current_user_id'::text, true), "
        "''::text))::uuid) AND (EXISTS ( SELECT 1\n"
        "   FROM (public.chat_participants participant\n"
        "     JOIN public.chats chat ON ((chat.id = participant.chat_id)))\n"
        "  WHERE ((participant.chat_id = chat_send_receipts.chat_id) AND "
        "(participant.user_id = chat_send_receipts.user_id))))))"
    ),
)


def _assert_receipt_contract(statements: list[str]) -> None:
    assert_baseline_operation_kinds(statements)
    selected = table_statements(statements, "chat_send_receipts")
    assert_exact_statements(selected, _EXPECTED_RECEIPT_SQL)
    table_position = selected.index(normalize_sql(_EXPECTED_RECEIPT_SQL[0]))
    force_position = selected.index(_EXPECTED_RECEIPT_SQL[-3])
    enable_position = selected.index(_EXPECTED_RECEIPT_SQL[-2])
    policy_position = selected.index(normalize_sql(_EXPECTED_RECEIPT_SQL[-1]))
    assert table_position < force_position < policy_position
    assert table_position < enable_position < policy_position
    for sql in _EXPECTED_RECEIPT_SQL[1:-3]:
        position = selected.index(normalize_sql(sql))
        assert table_position < position < min(force_position, enable_position)


def test_receipt_baseline_refuses_other_dialects_before_catalog_or_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = bind_baseline(monkeypatch, dialect="sqlite")
    with pytest.raises(RuntimeError, match="The MVP baseline requires PostgreSQL"):
        migration.upgrade()
    assert operations.bind_requests == 1
    assert operations.bind.reads == []
    assert operations.statements == []


def test_receipt_upgrade_emits_constrained_private_schema_before_rls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_receipt_contract(operations.statements)


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_receipt_contract_rejects_missing_or_duplicate_statements(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_receipt_contract(operations.statements)
    selected = table_statements(operations.statements, "chat_send_receipts")
    for statement in selected:
        changed = list(operations.statements)
        if mutation == "missing":
            changed.remove(statement)
        else:
            changed.append(statement)
        with pytest.raises(AssertionError):
            _assert_receipt_contract(changed)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("key_digest character varying(64) NOT NULL", "key_digest text"),
        ("message_id uuid,", "raw_key text, message_id uuid,"),
        (
            "REFERENCES public.messages(id) ON DELETE SET NULL",
            "REFERENCES public.messages(id) ON DELETE CASCADE",
        ),
        ("USING btree (expires_at, id)", "USING btree (expires_at)"),
        (
            "participant.user_id = chat_send_receipts.user_id",
            "true",
        ),
        ("FORCE ROW LEVEL SECURITY", "NO FORCE ROW LEVEL SECURITY"),
    ],
    ids=(
        "digest-type-and-nullability",
        "private-column-leak",
        "message-delete-action",
        "bounded-expiry-index",
        "participant-ownership",
        "forced-rls",
    ),
)
def test_receipt_contract_rejects_security_drift(
    monkeypatch: pytest.MonkeyPatch, before: str, after: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_receipt_contract(operations.statements)
    changed = [sql.replace(before, after) for sql in operations.statements]
    assert changed != operations.statements
    with pytest.raises(AssertionError):
        _assert_receipt_contract(changed)


def test_receipt_downgrade_refuses_before_any_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = bind_baseline(monkeypatch)
    assert_downgrade_refuses(migration, operations)


def test_receipt_model_registers_only_private_storage_columns() -> None:
    import app.models as models

    receipt_type = getattr(models, "ChatSendReceipt", None)
    assert receipt_type is not None, "Durable chat-send receipt model is not registered"
    table = receipt_type.__table__
    assert models.Base.metadata.tables["chat_send_receipts"] is table
    assert set(table.columns.keys()) == {
        "id",
        "chat_id",
        "user_id",
        "key_digest",
        "message_id",
        "completed_at",
        "expires_at",
    }
    assert not sa.inspect(receipt_type).relationships
    assert table.c.id.default is not None
    assert {column.name for column in table.columns if column.nullable} == {
        "message_id"
    }
    assert {
        (foreign_key.parent.name, foreign_key.target_fullname, foreign_key.ondelete)
        for foreign_key in table.foreign_keys
    } == {
        ("chat_id", "chats.id", "CASCADE"),
        ("user_id", "users.id", "CASCADE"),
        ("message_id", "messages.id", "SET NULL"),
    }


@pytest.mark.parametrize(
    "extra",
    [
        "ALTER TABLE PUBLIC.CHAT_SEND_RECEIPTS DISABLE ROW LEVEL SECURITY",
        "ALTER TABLE cHaT_sEnD_rEcEiPtS DISABLE ROW LEVEL SECURITY",
        "CREATE POLICY allow_all ON chat_send_receipts USING (true)",
    ],
)
def test_receipt_contract_rejects_append_only_overrides(
    monkeypatch: pytest.MonkeyPatch, extra: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_receipt_contract(operations.statements)
    with pytest.raises(AssertionError):
        _assert_receipt_contract([*operations.statements, extra])
