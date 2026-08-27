"""Notification queue dead-letter administration API contracts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import get_password_hash
from app.core.container import get_secure_audit_service_dep
from app.main import app
from app.models import NotificationQueueJob
from app.schemas.schemas import NotificationDeadLetterReplayIn
from app.services.notification_queue import (
    list_dead_lettered_jobs,
    purge_dead_lettered_jobs,
    retry_dead_lettered_jobs,
)

TEST_PASSWORD = "StrongPass123!"  # pragma: allowlist secret  # NOSONAR


async def _login(
    client: AsyncClient,
    user_factory,
    *,
    role: str,
) -> None:
    user = await user_factory(
        role=role,
        hashed_password=await get_password_hash(TEST_PASSWORD),
    )
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": user.email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200


def _dead_letter(
    *, kind: str = "news", error: str | None = None
) -> NotificationQueueJob:
    return NotificationQueueJob(
        kind=kind,
        record_id=uuid.uuid4(),
        locale="ru",
        enqueued_at=datetime.now(UTC),
        claimed_at=datetime.now(UTC),
        attempts=5,
        last_error=error,
        next_retry_at=datetime.now(UTC) + timedelta(minutes=5),
        dead_lettered=True,
    )


def test_dead_letter_job_ids_are_bounded_uuid_values_without_duplicates() -> None:
    identifier = uuid.uuid4()
    parsed = NotificationDeadLetterReplayIn(job_ids=[str(identifier)])
    assert parsed.job_ids == [identifier]

    with pytest.raises(ValueError, match="duplicate"):
        NotificationDeadLetterReplayIn(job_ids=[identifier, str(identifier)])
    with pytest.raises(ValueError):
        NotificationDeadLetterReplayIn(job_ids=["not-a-uuid"])
    with pytest.raises(ValueError):
        NotificationDeadLetterReplayIn(job_ids=[uuid.uuid4() for _ in range(101)])


@pytest.mark.asyncio
async def test_notification_dead_letter_routes_require_an_admin(
    root_client: AsyncClient,
    user_factory,
) -> None:
    unauthenticated = await root_client.get("/api/v1/notifications/admin/dead-letter")
    assert unauthenticated.status_code == 401

    await _login(root_client, user_factory, role="student")
    forbidden = await root_client.get("/api/v1/notifications/admin/dead-letter")
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_admin_lists_only_dead_letters_with_bounded_pagination_and_no_pii(
    root_client: AsyncClient,
    db_session: AsyncSession,
    user_factory,
) -> None:
    await _login(root_client, user_factory, role="admin")
    older = _dead_letter(error="SMTP failure for student@example.edu +7 999 123-45-67")
    newer = _dead_letter(kind="event", error=None)
    newer.enqueued_at = older.enqueued_at + timedelta(seconds=1)
    live = _dead_letter(error="must not be returned")
    live.dead_lettered = False
    db_session.add_all([older, newer, live])
    await db_session.commit()

    response = await root_client.get(
        "/api/v1/notifications/admin/dead-letter",
        params={"limit": 1, "offset": 0},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": str(newer.id),
                "kind": "event",
                "record_id": str(newer.record_id),
                "locale": "ru",
                "enqueued_at": newer.enqueued_at.isoformat().replace("+00:00", "Z"),
                "claimed_at": newer.claimed_at.isoformat().replace("+00:00", "Z"),
                "attempts": 5,
                "last_error": None,
                "next_retry_at": newer.next_retry_at.isoformat().replace("+00:00", "Z"),
            }
        ],
        "total": 2,
    }

    redacted = await root_client.get(
        "/api/v1/notifications/admin/dead-letter",
        params={"limit": 1, "offset": 1},
    )
    body = redacted.json()
    assert body["items"][0]["last_error"] == "Delivery failed"
    assert "student@example.edu" not in redacted.text
    assert "+7 999 123-45-67" not in redacted.text

    empty_page = await root_client.get(
        "/api/v1/notifications/admin/dead-letter",
        params={"limit": 1, "offset": 2},
    )
    assert empty_page.status_code == 200
    assert empty_page.json() == {"items": [], "total": 2}

    too_large = await root_client.get(
        "/api/v1/notifications/admin/dead-letter", params={"limit": 101}
    )
    assert too_large.status_code == 422


@pytest.mark.asyncio
async def test_retry_is_atomic_and_resets_selected_dead_letters(
    root_client: AsyncClient,
    db_session: AsyncSession,
    user_factory,
) -> None:
    await _login(root_client, user_factory, role="admin")
    first = _dead_letter(error="private diagnostic")
    second = _dead_letter(kind="event", error="private diagnostic")
    db_session.add_all([first, second])
    await db_session.commit()
    first_id = first.id
    second_id = second.id

    response = await root_client.post(
        "/api/v1/notifications/admin/dead-letter/retry",
        json={"job_ids": [str(first_id), str(second_id)]},
    )
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "affected_count": 2,
        "job_ids": [str(first_id), str(second_id)],
    }

    db_session.expire_all()
    retried = (
        (
            await db_session.execute(
                select(NotificationQueueJob).where(
                    NotificationQueueJob.id.in_([first_id, second_id])
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(retried) == 2
    for job in retried:
        assert job.dead_lettered is False
        assert job.claimed_at is None
        assert job.attempts == 0
        assert job.last_error is None
        assert job.next_retry_at is not None


@pytest.mark.asyncio
async def test_retry_rejects_stale_batch_without_partial_mutation(
    root_client: AsyncClient,
    db_session: AsyncSession,
    user_factory,
) -> None:
    await _login(root_client, user_factory, role="admin")
    selected = _dead_letter(error="still private")
    db_session.add(selected)
    await db_session.commit()

    response = await root_client.post(
        "/api/v1/notifications/admin/dead-letter/retry",
        json={"job_ids": [str(selected.id), str(uuid.uuid4())]},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Dead-letter selection is stale"
    await db_session.refresh(selected)
    assert selected.dead_lettered is True
    assert selected.attempts == 5
    assert selected.last_error == "still private"


@pytest.mark.asyncio
async def test_purge_is_atomic_and_deletes_only_selected_dead_letters(
    root_client: AsyncClient,
    db_session: AsyncSession,
    user_factory,
) -> None:
    await _login(root_client, user_factory, role="admin")
    selected = _dead_letter()
    retained = _dead_letter(kind="event")
    db_session.add_all([selected, retained])
    await db_session.commit()

    response = await root_client.post(
        "/api/v1/notifications/admin/dead-letter/purge",
        json={"job_ids": [str(selected.id)]},
    )
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "affected_count": 1,
        "job_ids": [str(selected.id)],
    }

    remaining = (await db_session.execute(select(NotificationQueueJob))).scalars().all()
    assert [job.id for job in remaining] == [retained.id]

    replayed_request = await root_client.post(
        "/api/v1/notifications/admin/dead-letter/purge",
        json={"job_ids": [str(selected.id)]},
    )
    assert replayed_request.status_code == 409
    remaining = (await db_session.execute(select(NotificationQueueJob))).scalars().all()
    assert [job.id for job in remaining] == [retained.id]


def test_openapi_declares_notification_dead_letter_operations() -> None:
    from app.main import app

    schema = app.openapi()
    paths = schema["paths"]
    assert set(paths["/api/v1/notifications/admin/dead-letter"]) == {"get"}
    assert set(paths["/api/v1/notifications/admin/dead-letter/retry"]) == {"post"}
    assert set(paths["/api/v1/notifications/admin/dead-letter/purge"]) == {"post"}
    assert (
        paths["/api/v1/notifications/admin/dead-letter"]["get"]["operationId"]
        == "listNotificationDeadLetters"
    )
    assert set(
        paths["/api/v1/notifications/admin/dead-letter"]["get"]["responses"]
    ) >= {"200", "401", "403", "422"}
    for action in ("retry", "purge"):
        assert set(
            paths[f"/api/v1/notifications/admin/dead-letter/{action}"]["post"][
                "responses"
            ]
        ) >= {"200", "401", "403", "409", "422"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    [retry_dead_lettered_jobs, purge_dead_lettered_jobs],
)
async def test_dead_letter_mutations_rollback_database_failures(operation) -> None:
    job = _dead_letter()
    job.id = uuid.uuid4()
    locked = MagicMock()
    locked.scalars.return_value.all.return_value = [job]
    db = AsyncMock()
    db.execute.side_effect = [locked, RuntimeError("write failed")]
    audit = MagicMock()
    audit.record_domain_event = AsyncMock()

    with pytest.raises(RuntimeError, match="write failed"):
        await operation(
            db,
            [job.id],
            audit=audit,
            actor_id=uuid.uuid4(),
        )

    db.rollback.assert_awaited_once_with()
    db.commit.assert_not_awaited()
    audit.record_domain_event.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    [retry_dead_lettered_jobs, purge_dead_lettered_jobs],
)
async def test_dead_letter_mutations_rollback_when_secure_audit_fails(
    operation,
) -> None:
    job = _dead_letter()
    job.id = uuid.uuid4()
    locked = MagicMock()
    locked.scalars.return_value.all.return_value = [job]
    db = AsyncMock()
    db.execute.side_effect = [locked, MagicMock()]
    audit = MagicMock()
    audit.record_domain_event = AsyncMock(side_effect=RuntimeError("audit failed"))

    with pytest.raises(RuntimeError, match="audit failed"):
        await operation(
            db,
            [job.id],
            audit=audit,
            actor_id=uuid.uuid4(),
        )

    audit.record_domain_event.assert_awaited_once()
    db.rollback.assert_awaited_once_with()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_dead_letter_mutations_are_safely_attributed(
    root_client: AsyncClient,
    db_session: AsyncSession,
    user_factory,
) -> None:
    admin = await user_factory(
        role="admin",
        hashed_password=await get_password_hash(TEST_PASSWORD),
    )
    login = await root_client.post(
        "/api/v1/auth/login",
        data={"username": admin.email, "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    retry_job = _dead_letter(error="private retry diagnostic")
    purge_job = _dead_letter(error="private purge diagnostic")
    db_session.add_all([retry_job, purge_job])
    await db_session.commit()
    audit = MagicMock()
    audit.record_domain_event = AsyncMock()
    app.dependency_overrides[get_secure_audit_service_dep] = lambda: audit

    try:
        retry = await root_client.post(
            "/api/v1/notifications/admin/dead-letter/retry",
            json={"job_ids": [str(retry_job.id)]},
        )
        purge = await root_client.post(
            "/api/v1/notifications/admin/dead-letter/purge",
            json={"job_ids": [str(purge_job.id)]},
        )
    finally:
        app.dependency_overrides.pop(get_secure_audit_service_dep, None)

    assert retry.status_code == 200
    assert purge.status_code == 200
    assert audit.record_domain_event.await_count == 2
    expected = [
        (
            "NOTIFICATION_DEAD_LETTER_RETRY",
            retry_job.id,
        ),
        (
            "NOTIFICATION_DEAD_LETTER_PURGE",
            purge_job.id,
        ),
    ]
    for call, (action, job_id) in zip(
        audit.record_domain_event.await_args_list,
        expected,
        strict=True,
    ):
        digest = sha256(str(job_id).encode("ascii")).hexdigest()
        assert call.kwargs["event_type"] == action
        assert call.kwargs["aggregate_type"] == "notification_dead_letter_batch"
        assert call.kwargs["aggregate_id"] == digest
        assert call.kwargs["actor_id"] == admin.id
        assert call.kwargs["payload"] == {"batch_count": 1}
        assert str(job_id) not in str(call)
        assert "private" not in str(call)


def test_dead_letter_public_serialization_preserves_aware_values_and_nulls() -> None:
    from app.api.notification_dead_letters import _to_public_job

    job = _dead_letter(error="private")
    job.id = uuid.uuid4()
    job.claimed_at = None
    job.next_retry_at = None

    output = _to_public_job(job)

    assert output.enqueued_at.tzinfo is UTC
    assert output.claimed_at is None
    assert output.next_retry_at is None
    assert output.last_error == "Delivery failed"


@pytest.mark.asyncio
async def test_dead_letter_page_and_total_use_one_database_snapshot() -> None:
    """Even an empty offset page must carry the count from the same statement."""
    result = MagicMock()
    result.all.return_value = [(None, 2)]
    db = AsyncMock()
    db.execute.return_value = result

    jobs, total = await list_dead_lettered_jobs(db, limit=20, offset=100)

    assert jobs == []
    assert total == 2
    db.execute.assert_awaited_once()
    statement = str(db.execute.await_args.args[0]).lower()
    assert "left outer join" in statement
    assert "count(" in statement
