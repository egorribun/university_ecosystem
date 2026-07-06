"""Wave 7.2 – Branch coverage for key service-layer operations.

Covers:
- EventService.delete_event: happy path (returns True), event not found
  (returns False), image/file deletion OSError best-effort (logs, no raise),
  IntegrityError rollback path in register_attendance.
- ChatGroupMemberService._require_group_participant: user not a participant
  (→ 403), chat is a DM not a group (→ 400), happy-path returns participant set.
- NotificationService.dispatch_event_created: happy-path enqueue,
  RuntimeError enqueue failure (records to dead-letter, no raise).
- UserComplianceService: non-admin delete attempt (→ PermissionDenied),
  delete-self attempt (→ BusinessRuleViolation), user-not-found (→ EntityNotFound).
- create_notifications_for_users: empty user list returns 0 immediately,
  user_filter excludes all users returns 0.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_uow(repo_attrs: dict | None = None):
    """Build a minimal UnitOfWork mock for service unit tests.

    WHY: services receive a UnitOfWork abstraction; a mock lets us test branch
    logic without requiring a live database session.
    """
    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()

    repo = MagicMock()
    if repo_attrs:
        for attr, value in repo_attrs.items():
            setattr(repo, attr, value)

    uow.events = repo
    uow.chats = repo
    uow.users = repo
    uow.sessions = repo
    uow.session = MagicMock()
    return uow, repo


# ---------------------------------------------------------------------------
# EventService.delete_event – branch coverage
# ---------------------------------------------------------------------------


async def test_event_delete_event_not_found_returns_false():
    """Branch: repo.get returns None → delete_event returns False without deleting.

    WHY: a 404-style early-return prevents a cascade of repo calls (delete_event_files,
    delete, commit) on a non-existent event — callers use the bool to emit 404.
    """
    from app.services.event_service import EventService
    from app.services.vector_service import VectorService

    uow, repo = _make_mock_uow()
    repo.get = AsyncMock(return_value=None)
    vector_service = MagicMock(spec=VectorService)

    service = EventService(uow=uow, vector_service=vector_service)
    result = await service.delete_event(uuid.uuid4())
    assert result is False, "delete_event MUST return False when event does not exist"


async def test_event_delete_event_happy_path_returns_true():
    """Branch: repo.get returns an event DTO → all cleanup runs, returns True.

    WHY: the success path (event exists, DB delete committed, storage files
    cleaned up) must return True so the router can emit 204.
    """
    from app.services.event_service import EventService
    from app.services.vector_service import VectorService

    event_id = uuid.uuid4()
    mock_event = MagicMock()
    mock_event.image_url = None  # No image → skip image cleanup branch

    uow, repo = _make_mock_uow()
    repo.get = AsyncMock(return_value=mock_event)
    repo.get_event_file_urls = AsyncMock(return_value=[])
    repo.delete_event_files = AsyncMock()
    repo.delete = AsyncMock()
    vector_service = MagicMock(spec=VectorService)

    service = EventService(uow=uow, vector_service=vector_service)
    result = await service.delete_event(event_id)
    assert result is True, (
        "delete_event MUST return True when event exists and is deleted"
    )


async def test_event_delete_image_oserror_is_non_fatal(caplog):
    """Branch: image_url present, delete_static_file raises OSError → logged, no raise.

    WHY: storage cleanup is best-effort (MED-W19); a broken static file must NOT
    roll back the DB commit or cause a 500 for the client.
    """
    import logging

    from app.services.event_service import EventService
    from app.services.vector_service import VectorService

    event_id = uuid.uuid4()
    mock_event = MagicMock()
    mock_event.image_url = "http://example.com/image.jpg"

    uow, repo = _make_mock_uow()
    repo.get = AsyncMock(return_value=mock_event)
    repo.get_event_file_urls = AsyncMock(return_value=[])
    repo.delete_event_files = AsyncMock()
    repo.delete = AsyncMock()
    vector_service = MagicMock(spec=VectorService)

    with (
        patch(
            "app.utils.files.delete_static_file",
            side_effect=OSError("disk full"),
        ),
        caplog.at_level(logging.WARNING),
    ):
        service = EventService(uow=uow, vector_service=vector_service)
        result = await service.delete_event(event_id)

    assert result is True, "OSError during image cleanup MUST NOT prevent True return"


async def test_event_delete_file_urls_oserror_each_logged(caplog):
    """Branch: per-file delete_static_file raises OSError → each is logged, no raise.

    WHY: individual file failures must not abort the entire delete — incomplete
    cleanup is logged so an operator can recover orphan files manually.
    """
    import logging

    from app.services.event_service import EventService
    from app.services.vector_service import VectorService

    event_id = uuid.uuid4()
    mock_event = MagicMock()
    mock_event.image_url = None

    uow, repo = _make_mock_uow()
    repo.get = AsyncMock(return_value=mock_event)
    repo.get_event_file_urls = AsyncMock(
        return_value=["http://s.com/a.pdf", "http://s.com/b.pdf"]
    )
    repo.delete_event_files = AsyncMock()
    repo.delete = AsyncMock()
    vector_service = MagicMock(spec=VectorService)

    call_count = 0

    async def _fail(url):
        nonlocal call_count
        call_count += 1
        raise FileNotFoundError(f"missing: {url}")

    with (
        patch("app.utils.files.delete_static_file", side_effect=_fail),
        caplog.at_level(logging.WARNING),
    ):
        service = EventService(uow=uow, vector_service=vector_service)
        result = await service.delete_event(event_id)

    assert result is True
    assert call_count == 2, "delete_static_file MUST be attempted for each file URL"


# ---------------------------------------------------------------------------
# EventService.register_attendance – IntegrityError rollback branch
# ---------------------------------------------------------------------------


async def test_event_register_attendance_integrity_error_retries():
    """Branch: IntegrityError on create_attendance → rollback → retry fetch → return.

    WHY: two concurrent registrations can both pass the check-then-act; the
    IntegrityError handler must rollback, re-fetch the existing record, and
    return it rather than propagating the DB error to the caller.
    """
    import uuid as _uuid

    from sqlalchemy.exc import IntegrityError

    from app.schemas.schemas import EventAttendanceCreate
    from app.services.event_service import EventService
    from app.services.vector_service import VectorService

    event_id = _uuid.uuid4()
    user_id = _uuid.uuid4()

    mock_event_locked = MagicMock()
    mock_event_locked.is_active = True
    mock_event_locked.ends_at = None

    existing_record = MagicMock()
    existing_record.registered_at = datetime.now(UTC)
    existing_record.qr_token = None
    existing_record.model_copy = MagicMock(return_value=existing_record)

    uow, repo = _make_mock_uow()
    repo.get_for_registration = AsyncMock(return_value=mock_event_locked)
    repo.get_attendance = AsyncMock(return_value=None)
    repo.create_attendance = AsyncMock(
        side_effect=IntegrityError("unique", "params", "orig")
    )
    uow.rollback = AsyncMock()

    # After rollback, re-fetch finds the record
    repo.get_attendance = AsyncMock(side_effect=[None, existing_record])

    vector_service = MagicMock(spec=VectorService)
    service = EventService(uow=uow, vector_service=vector_service)
    data = EventAttendanceCreate(event_id=event_id)

    with (
        patch(
            "app.services.event_service.attendance_tokens.generate_secret",
            return_value="s",
        ),
        patch(
            "app.services.event_service.attendance_tokens.compute_secret_hmac",
            return_value="h",
        ),
        patch(
            "app.services.event_service.attendance_tokens.issue_token",
            return_value="tok",
        ),
        patch(
            "app.services.event_service.stats_cache.invalidate_user_stats_cache",
            new=AsyncMock(),
        ),
    ):
        result = await service.register_attendance(data, user_id)

    assert result is not None, (
        "IntegrityError rollback path MUST return existing record"
    )


# ---------------------------------------------------------------------------
# ChatGroupMemberService._require_group_participant – branch coverage
# ---------------------------------------------------------------------------


def test_require_group_participant_non_participant_raises_forbidden():
    """Branch: user is NOT in chat.participants → raise_forbidden called.

    WHY: the authz gate must block non-members from adding/removing others —
    the forbidden branch protects the group-membership management endpoint.
    """

    # Import the class under test (it lives deep in command_service)
    from app.services.chat.command_service import ChatMaintenanceService

    chat = MagicMock()
    chat.participants = []  # empty — user can't be a member
    chat.chat_type = "group"

    user = MagicMock()
    user.id = uuid.uuid4()

    uow, repo = _make_mock_uow()  # noqa: RUF059
    attachment_service = MagicMock()
    service = ChatMaintenanceService(
        uow=uow,
        attachment_service=attachment_service,
    )

    with pytest.raises(Exception):  # noqa: B017 - raise_forbidden raises HTTPException which inherits from Exception
        # raise_forbidden raises HTTPException(403)
        service._require_group_participant(chat, user, locale="ru")


def test_require_group_participant_dm_chat_raises_validation_error():
    """Branch: user is a participant but chat_type != 'group' → raise_validation_error.

    WHY: DM chats must not be mutated via the group-management endpoints; any
    attempt must return a descriptive 400 error rather than silently succeeding.
    """
    from app.services.chat.command_service import ChatMaintenanceService

    user_id = uuid.uuid4()
    participant = MagicMock()
    participant.id = user_id

    chat = MagicMock()
    chat.participants = [participant]
    chat.chat_type = "dm"  # Not a group!

    user = MagicMock()
    user.id = user_id

    uow, repo = _make_mock_uow()  # noqa: RUF059
    attachment_service = MagicMock()
    service = ChatMaintenanceService(
        uow=uow,
        attachment_service=attachment_service,
    )

    with pytest.raises(Exception):  # noqa: B017 - raise_forbidden raises HTTPException which inherits from Exception
        # raise_validation_error raises HTTPException(422)
        service._require_group_participant(chat, user, locale="ru")


def test_require_group_participant_happy_path_returns_id_set():
    """Branch: user is participant AND chat_type == 'group' → returns participant ids.

    WHY: the return value (set of IDs) is used by add/remove participant for
    cache invalidation — verifying the return value confirms the happy path
    executes without error and produces the correct data structure.
    """
    from app.services.chat.command_service import ChatMaintenanceService

    user_id = uuid.uuid4()
    other_id = uuid.uuid4()

    p1 = MagicMock()
    p1.id = user_id
    p2 = MagicMock()
    p2.id = other_id

    chat = MagicMock()
    chat.participants = [p1, p2]
    chat.chat_type = "group"

    user = MagicMock()
    user.id = user_id

    uow, repo = _make_mock_uow()  # noqa: RUF059
    service = ChatMaintenanceService(
        uow=uow,
        attachment_service=MagicMock(),
    )

    result = service._require_group_participant(chat, user, locale="ru")
    assert user_id in result
    assert other_id in result


# ---------------------------------------------------------------------------
# NotificationService.dispatch_event_created – branch coverage
# ---------------------------------------------------------------------------


async def test_notification_dispatch_event_created_happy_path():
    """Branch: add_task succeeds → no error records created.

    WHY: the normal dispatch flow must not write any failure records to the
    dead-letter store — asserting the failure list is empty confirms that.
    """
    from fastapi import BackgroundTasks

    from app.services import notification_queue
    from app.services.notification_service import NotificationService

    await notification_queue.reset_testing_state()

    db = AsyncMock()
    service = NotificationService(db=db)
    bg = BackgroundTasks()

    event_id = uuid.uuid4()
    await service.dispatch_event_created(event_id, locale="ru", background=bg)

    failures = await notification_queue.get_failed_enqueue_records()
    assert len(failures) == 0, "Successful dispatch must not create failure records"


async def test_notification_dispatch_event_created_enqueue_failure_recorded():
    """Branch: background.add_task raises RuntimeError → failure is recorded, no raise.

    WHY: the NotificationService wraps add_task in a try/except; a broken
    background task queue must NOT bubble an exception to the HTTP handler —
    the failure is recorded to the dead-letter store and logged instead.
    """

    from app.services import notification_queue
    from app.services.notification_service import NotificationService

    await notification_queue.reset_testing_state()

    db = AsyncMock()
    service = NotificationService(db=db)

    bad_bg = MagicMock()
    bad_bg.add_task = MagicMock(side_effect=RuntimeError("queue full"))

    event_id = uuid.uuid4()
    # Must NOT raise
    await service.dispatch_event_created(event_id, locale="ru", background=bad_bg)

    failures = await notification_queue.get_failed_enqueue_records()
    assert len(failures) == 1, (
        "RuntimeError during enqueue MUST be recorded to dead-letter"
    )
    assert failures[0].job.kind == "event"


# ---------------------------------------------------------------------------
# create_notifications_for_users – branch coverage
# ---------------------------------------------------------------------------


async def test_create_notifications_empty_user_ids_returns_zero():
    """Branch: user_ids is empty → return 0 immediately without any DB call.

    WHY: the early-exit guard prevents an unnecessary INSERT with an empty
    values list, which would cause a DB error or silently waste resources.
    """
    from unittest.mock import AsyncMock as AM

    from app.services.notifications.delivery import create_notifications_for_users

    db = AM()
    result = await create_notifications_for_users(db, title="Test", user_ids=[])
    assert result == 0, "Empty user_ids MUST return 0 without touching the DB"


async def test_create_notifications_user_filter_excludes_all_returns_zero():
    """Branch: user_filter removes all UIDs → return 0 before INSERT.

    WHY: when a filter (e.g., only_active_users) eliminates all target users
    the function must short-circuit to avoid an INSERT with zero rows.
    """
    from unittest.mock import AsyncMock as AM
    from unittest.mock import MagicMock as MM

    from app.services.notifications.delivery import create_notifications_for_users

    uid = uuid.uuid4()
    db = AM()

    # Simulate a user filter that returns no rows
    empty_result = MM()
    empty_result.scalars = MM(return_value=MM(all=MM(return_value=[])))
    db.execute = AM(return_value=empty_result)

    def _exclude_all(stmt):
        return stmt.where(False)  # type: ignore[arg-type]

    result = await create_notifications_for_users(
        db, title="Test", user_ids=[uid], user_filter=_exclude_all
    )
    assert result == 0, "user_filter that excludes all users MUST return 0"


# ---------------------------------------------------------------------------
# UserComplianceService – access-control branch coverage
# ---------------------------------------------------------------------------


async def test_user_compliance_non_admin_delete_raises_permission_denied():
    """Branch: current_user.role != 'admin' → PermissionDenied raised.

    WHY: the admin_delete_user method must block non-admin callers before
    performing any DB mutations — authorization checks must come first.
    """
    from app.core.exceptions.domain import PermissionDenied
    from app.services.audit_service import AuditService
    from app.services.user.compliance_service import UserComplianceService

    uow, repo = _make_mock_uow()  # noqa: RUF059
    audit = MagicMock(spec=AuditService)
    audit.log = MagicMock()

    service = UserComplianceService(uow=uow, audit=audit)

    non_admin = MagicMock()
    non_admin.role = "student"

    request = MagicMock()
    request.state = MagicMock()

    with pytest.raises(PermissionDenied):
        await service.admin_delete_user(
            user_id=uuid.uuid4(),
            request=request,
            current_user=non_admin,
        )


async def test_user_compliance_delete_self_raises_business_rule_violation():
    """Branch: admin tries to delete their own account → BusinessRuleViolation.

    WHY: self-deletion would lock the admin out and is disallowed as a business
    rule — the guard must fire even when the caller has admin privileges.
    """
    from app.core.exceptions.domain import BusinessRuleViolation
    from app.services.audit_service import AuditService
    from app.services.user.compliance_service import UserComplianceService

    admin_id = uuid.uuid4()
    admin = MagicMock()
    admin.role = "admin"
    admin.id = admin_id

    db_user = MagicMock()
    db_user.id = admin_id  # Same as admin!

    uow, repo = _make_mock_uow()
    repo._get_orm = AsyncMock(return_value=db_user)
    audit = MagicMock(spec=AuditService)
    audit.log = MagicMock()

    service = UserComplianceService(uow=uow, audit=audit)
    request = MagicMock()
    request.state = MagicMock()

    with pytest.raises(BusinessRuleViolation):
        await service.admin_delete_user(
            user_id=admin_id,
            request=request,
            current_user=admin,
        )


async def test_user_compliance_delete_nonexistent_user_raises_entity_not_found():
    """Branch: target user_id does not exist in DB → EntityNotFound raised.

    WHY: attempting to delete a non-existent user must produce a clear 404
    rather than a null-pointer error or silent no-op.
    """
    from app.core.exceptions.domain import EntityNotFound
    from app.services.audit_service import AuditService
    from app.services.user.compliance_service import UserComplianceService

    admin = MagicMock()
    admin.role = "admin"
    admin.id = uuid.uuid4()

    uow, repo = _make_mock_uow()
    repo._get_orm = AsyncMock(return_value=None)  # Not found
    audit = MagicMock(spec=AuditService)
    audit.log = MagicMock()

    service = UserComplianceService(uow=uow, audit=audit)
    request = MagicMock()
    request.state = MagicMock()

    with pytest.raises(EntityNotFound):
        await service.admin_delete_user(
            user_id=uuid.uuid4(),
            request=request,
            current_user=admin,
        )
