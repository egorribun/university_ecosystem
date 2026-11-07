"""Signed audit writes never require mutation rights on persisted audit rows."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from app.models.logs import DataAccessLog
from app.services.audit_service import SecureAuditService


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", ["single", "batch"])
@pytest.mark.parametrize("time_kind", ["default", "naive", "offset"])
@pytest.mark.parametrize("uuid_kind", ["object", "uppercase", "compact"])
async def test_audit_writer_inserts_signed_rows_without_updates(
    db_session, user_factory, writer: str, time_kind: str, uuid_kind: str
) -> None:
    signing_key = secrets.token_bytes(32)
    service = SecureAuditService(signing_key=signing_key)
    resource_id = str(uuid4())
    timestamp = datetime.now(UTC)
    actor = await user_factory()
    subject = await user_factory()
    actor_id, subject_id, explicit_id = actor.id, subject.id, uuid4()

    def supplied_uuid(value):
        if uuid_kind == "uppercase":
            return str(value).upper()
        if uuid_kind == "compact":
            return value.hex
        return value

    entry = {
        "actor_user_id": supplied_uuid(actor_id),
        "subject_user_id": supplied_uuid(subject_id),
        "resource_type": "profile",
        "resource_id": resource_id,
        "action": "read",
        "context": {"nested": {7: ("before", "after")}},
    }
    if time_kind == "naive":
        entry["created_at"] = timestamp.replace(tzinfo=None)
    elif time_kind == "offset":
        entry["created_at"] = timestamp.astimezone(timezone(timedelta(hours=3)))
    if writer == "batch":
        entry["id"] = supplied_uuid(explicit_id)
    original_entry = copy.deepcopy(entry)
    inserted = []

    def prohibit_audit_mutations(
        _connection, _cursor, _statement, _parameters, context, _executemany
    ):
        compiled = context.compiled
        if compiled is None:
            return
        statement = compiled.statement
        table = getattr(statement, "table", None)
        if table is None or table.name != DataAccessLog.__tablename__:
            return
        assert not getattr(statement, "is_update", False)
        assert not getattr(statement, "is_delete", False)
        if getattr(statement, "is_insert", False):
            inserted.append(statement)

    bind = db_session.get_bind()
    event.listen(bind, "before_cursor_execute", prohibit_audit_mutations)
    try:
        if writer == "single":
            written = [await service.create_log(db_session, **entry)]
        else:
            written = await service.create_logs(db_session, entries=[entry])
        assert len(written) == 1
        if writer == "single":
            assert written[0].id.version == 7
        else:
            assert written[0].id == explicit_id
        assert written[0].actor_user_id == actor_id
        assert written[0].subject_user_id == subject_id
        assert service.verify_integrity(written[0]) is True
        await db_session.flush()
        db_session.expunge_all()
        persisted = await db_session.scalar(
            select(DataAccessLog).where(DataAccessLog.resource_id == resource_id)
        )
        assert persisted is not None
        assert persisted.id == written[0].id
        assert persisted.signature == written[0].signature
        assert service.verify_integrity(persisted) is True
        expected_payload = json.dumps(
            {
                "version": 2,
                "id": str(persisted.id),
                "actor_user_id": str(actor_id),
                "subject_user_id": str(subject_id),
                "resource_type": "profile",
                "resource_id": resource_id,
                "action": "read",
                "context": {"nested": {"7": ["before", "after"]}},
                "ip_address": "",
                "user_agent": "",
                "created_at": persisted.created_at.isoformat(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        expected_signature = (
            "v2:"
            + hmac.new(
                signing_key, expected_payload.encode("utf-8"), hashlib.sha256
            ).hexdigest()
        )
        assert persisted.signature == expected_signature
        assert persisted.context == {"nested": {"7": ["before", "after"]}}
        assert persisted.created_at.replace(tzinfo=UTC) == (
            written[0].created_at.replace(tzinfo=UTC)
        )
        if time_kind != "default":
            assert persisted.created_at.replace(tzinfo=UTC) == timestamp
        assert inserted
        assert entry == original_entry
    finally:
        event.remove(bind, "before_cursor_execute", prohibit_audit_mutations)


@pytest.mark.asyncio
async def test_audit_batch_preserves_input_order_explicit_ids_and_rollback(
    db_session,
) -> None:
    service = SecureAuditService(signing_key=secrets.token_bytes(32))
    resource_id = str(uuid4())
    entries = [
        {
            "id": uuid4(),
            "resource_type": "profile",
            "resource_id": resource_id,
            "action": action,
            "context": {"position": position},
        }
        for position, action in enumerate(("read", "export", "read"))
    ]
    original_entries = copy.deepcopy(entries)
    written = await service.create_logs(db_session, entries=entries)
    assert [row.id for row in written] == [entry["id"] for entry in entries]
    assert [row.action for row in written] == [entry["action"] for entry in entries]
    assert all(service.verify_integrity(row) for row in written)
    assert entries == original_entries
    await db_session.rollback()
    assert (
        await db_session.scalar(
            select(DataAccessLog).where(DataAccessLog.resource_id == resource_id)
        )
        is None
    )
