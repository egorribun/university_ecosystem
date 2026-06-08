"""Coverage for ``app.services.data_access`` — audit-log write/export helpers.

Mix of three proven patterns (Track C, session 6):
- pure-fn        : ``serialize_access_logs_csv`` / ``_normalize_time``
- AsyncMock-repo : ``log_data_access`` / ``batch_log_data_access`` commit-flag branches
- real-DB        : export + cleanup paths via ``db_session`` + ``user_factory``

FK gotcha (#27): ``data_access_logs.actor_user_id`` / ``subject_user_id`` FK is
enforced on the PostgreSQL integration tier (not SQLite). Every directly-seeded
row threads a real ``user_factory()`` id. Partition gotcha (#15):
``data_access_logs`` is RANGE-partitioned by ``created_at`` on PG, so seeded rows
use a *recent* timestamp.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.logs import DataAccessLog
from app.schemas.dtos.audit import DataAccessLogDTO
from app.services.data_access import (
    _normalize_time,
    batch_log_data_access,
    cleanup_access_logs,
    export_access_logs,
    export_access_logs_stream,
    log_data_access,
    serialize_access_logs_csv,
)


def _request(host: str | None = "1.2.3.4", user_agent: str | None = "pytest-agent"):
    """Minimal ``fastapi.Request`` stand-in exposing ``.client.host`` + ``.headers.get``."""
    client = SimpleNamespace(host=host) if host is not None else None
    headers = {"user-agent": user_agent} if user_agent is not None else {}
    return SimpleNamespace(client=client, headers=headers)


def _dto(**overrides) -> DataAccessLogDTO:
    base = {
        "id": uuid.uuid4(),
        "actor_user_id": uuid.uuid4(),
        "subject_user_id": None,
        "resource_type": "user",
        "resource_id": "1",
        "action": "read",
        "context": {"k": "v"},
        "ip_address": "1.1.1.1",
        "user_agent": "UA",
        "created_at": datetime.now(UTC),
        "signature": "sig",
    }
    base.update(overrides)
    return DataAccessLogDTO(**base)


# --------------------------------------------------------------------------- #
# _normalize_time — pure                                                       #
# --------------------------------------------------------------------------- #


def test_normalize_time_none_naive_and_aware():
    assert _normalize_time(None) is None

    naive = datetime(2026, 1, 2, 3, 4, 5)
    normalized = _normalize_time(naive)
    assert normalized is not None and normalized.tzinfo == UTC

    aware = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert _normalize_time(aware) == aware


# --------------------------------------------------------------------------- #
# serialize_access_logs_csv — pure                                            #
# --------------------------------------------------------------------------- #


def test_serialize_access_logs_csv_header_and_rows():
    csv_str = serialize_access_logs_csv([_dto(action="read"), _dto(action="write")])
    lines = csv_str.strip().splitlines()
    assert lines[0].startswith("created_at,actor_user_id,subject_user_id,resource_type")
    assert len(lines) == 3  # header + 2 rows
    assert "read" in csv_str
    assert "write" in csv_str


def test_serialize_access_logs_csv_empty_is_header_only():
    csv_str = serialize_access_logs_csv([])
    assert csv_str.strip().splitlines() == [
        "created_at,actor_user_id,subject_user_id,resource_type,resource_id,"
        "action,ip_address,user_agent,context"
    ]


# --------------------------------------------------------------------------- #
# log_data_access — commit-flag + ip/ua extraction (AsyncMock repo)            #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_log_data_access_skips_commit_when_commit_false():
    db = MagicMock()
    db.commit = AsyncMock()
    fake_dto = MagicMock()
    with patch("app.services.data_access.AuditRepository") as mock_repo_cls:
        instance = mock_repo_cls.return_value
        instance.create = AsyncMock(return_value=fake_dto)
        result = await log_data_access(
            db,
            actor_user_id=uuid.uuid4(),
            subject_user_id=None,
            resource_type="user",
            action="read",
            request=_request(host="9.9.9.9", user_agent="UA"),
            commit=False,
        )

    assert result is fake_dto
    instance.create.assert_awaited_once()
    created = instance.create.call_args.args[0]
    assert created["resource_type"] == "user"
    assert created["action"] == "read"
    assert created["ip_address"] == "9.9.9.9"
    assert created["user_agent"] == "UA"
    assert len(created["signature"]) == 64  # real HMAC-SHA256 hex digest
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_log_data_access_handles_missing_client_and_commits():
    db = MagicMock()
    db.commit = AsyncMock()
    with patch("app.services.data_access.AuditRepository") as mock_repo_cls:
        instance = mock_repo_cls.return_value
        instance.create = AsyncMock(return_value=MagicMock())
        await log_data_access(
            db,
            actor_user_id=None,
            subject_user_id=None,
            resource_type="system",
            action="cleanup",
            request=_request(host=None, user_agent=None),
            commit=True,
        )

    created = instance.create.call_args.args[0]
    assert created["ip_address"] == "unknown"  # request.client is None
    assert created["user_agent"] is None  # header absent
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_log_data_access_persists_and_signs(db_session, user_factory):
    actor = await user_factory()
    subject = await user_factory()
    dto = await log_data_access(
        db_session,
        actor_user_id=actor.id,
        subject_user_id=subject.id,
        resource_type="profile",
        action="update",
        request=_request(host="1.2.3.4", user_agent="real-agent"),
        resource_id="42",
        context={"field": "name"},
    )
    assert dto.actor_user_id == actor.id
    assert dto.subject_user_id == subject.id
    assert dto.action == "update"
    assert dto.resource_id == "42"
    assert dto.signature and len(dto.signature) == 64


# --------------------------------------------------------------------------- #
# batch_log_data_access — empty short-circuit + commit-flag                    #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_batch_log_data_access_empty_is_noop():
    db = MagicMock()
    db.commit = AsyncMock()
    with patch("app.services.data_access.AuditRepository") as mock_repo_cls:
        await batch_log_data_access(db, entries=[], request=_request())
        mock_repo_cls.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_log_data_access_builds_entries_and_honors_commit_flag():
    db = MagicMock()
    db.commit = AsyncMock()
    with patch("app.services.data_access.AuditRepository") as mock_repo_cls:
        instance = mock_repo_cls.return_value
        instance.batch_create = AsyncMock()
        await batch_log_data_access(
            db,
            entries=[
                {"actor_user_id": uuid.uuid4(), "resource_type": "user", "action": "a"},
                {"resource_type": None, "action": None, "resource_id": None},
            ],
            request=_request(host="5.5.5.5", user_agent="batch-agent"),
            commit=False,
        )

    instance.batch_create.assert_awaited_once()
    built = instance.batch_create.call_args.args[0]
    assert len(built) == 2
    assert all(entry["ip_address"] == "5.5.5.5" for entry in built)
    assert all(len(entry["signature"]) == 64 for entry in built)
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_log_data_access_persists_real_rows(db_session, user_factory):
    actor = await user_factory()
    await batch_log_data_access(
        db_session,
        entries=[
            {"actor_user_id": actor.id, "resource_type": "user", "action": "read"},
            {"actor_user_id": actor.id, "resource_type": "news", "action": "list"},
        ],
        request=_request(),
        commit=True,
    )
    logs = await export_access_logs(db_session, actor_user_id=actor.id)
    assert len(logs) == 2


# --------------------------------------------------------------------------- #
# cleanup_access_logs — retention guard + prune-returns-zero                   #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("retention", [0, -5])
async def test_cleanup_access_logs_non_positive_retention_returns_zero(retention):
    # No DB access required: the guard returns before touching a session.
    assert await cleanup_access_logs(db=None, retention_days=retention) == 0


@pytest.mark.asyncio
async def test_cleanup_access_logs_keeps_recent_rows(db_session, user_factory):
    actor = await user_factory()
    db_session.add(
        DataAccessLog(
            actor_user_id=actor.id,
            resource_type="user",
            action="read",
            created_at=datetime.now(UTC),  # recent → newer than the 180-day cutoff
        )
    )
    await db_session.flush()
    pruned = await cleanup_access_logs(db=db_session, retention_days=180)
    assert pruned == 0


# --------------------------------------------------------------------------- #
# export_access_logs / _stream — filters + DTO + CSV-injection sanitize        #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_export_access_logs_applies_filters(db_session, user_factory):
    actor = await user_factory()
    other = await user_factory()
    now = datetime.now(UTC)
    db_session.add_all(
        [
            DataAccessLog(
                actor_user_id=actor.id,
                resource_type="user",
                action="read",
                created_at=now,
            ),
            DataAccessLog(
                actor_user_id=other.id,
                resource_type="news",
                action="list",
                created_at=now,
            ),
        ]
    )
    await db_session.flush()

    scoped = await export_access_logs(
        db_session,
        actor_user_id=actor.id,
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=1),
    )
    assert [row.actor_user_id for row in scoped] == [actor.id]

    # subject_user_id filter branch — no row has this subject, so it scopes to []
    by_subject = await export_access_logs(db_session, subject_user_id=actor.id)
    assert by_subject == []

    everything = await export_access_logs(db_session, limit=10)
    assert len(everything) == 2


@pytest.mark.asyncio
async def test_export_access_logs_stream_sanitizes_csv_injection(
    db_session, user_factory
):
    actor = await user_factory()
    db_session.add(
        DataAccessLog(
            actor_user_id=actor.id,
            resource_type="=danger",  # formula-injection prefix
            resource_id="1",
            action="read",
            context={"k": "v"},
            ip_address="1.1.1.1",
            user_agent="@evil",
            created_at=datetime.now(UTC),
        )
    )
    await db_session.flush()

    chunks = [chunk async for chunk in export_access_logs_stream(db_session)]
    full = "".join(chunks)
    assert full.startswith("created_at,actor_user_id")  # header row
    assert "\t=danger" in full  # resource_type neutralized
    assert "\t@evil" in full  # user_agent neutralized


@pytest.mark.asyncio
async def test_export_access_logs_stream_applies_all_filters(db_session, user_factory):
    actor = await user_factory()
    now = datetime.now(UTC)
    db_session.add(
        DataAccessLog(
            actor_user_id=actor.id,
            resource_type="user",
            action="read",
            created_at=now,
        )
    )
    await db_session.flush()

    # Exercise every filter branch (start/end/actor/subject). subject scopes to
    # the actor's id (no matching row) → the stream yields only the header.
    chunks = [
        chunk
        async for chunk in export_access_logs_stream(
            db_session,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=1),
            actor_user_id=actor.id,
            subject_user_id=actor.id,
        )
    ]
    assert "".join(chunks).startswith("created_at,actor_user_id")
