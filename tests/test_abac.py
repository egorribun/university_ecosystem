"""Unit tests for Context-Aware Access Guard (ABAC + ReBAC)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status

from app.auth.abac import ContextAwareAccessGuard, check_control_work_access
from app.auth.rbac import PermissionChecker, SpiceDBUnavailableError
from app.core.config import settings


class DummyLesson:
    """Dummy lesson model for schedule testing."""

    def __init__(
        self,
        start_time: datetime,
        end_time: datetime,
        lesson_id: uuid.UUID | str | None = None,
    ):
        self.id = lesson_id or uuid.uuid4()
        self.start_time = start_time
        self.end_time = end_time


@pytest.fixture
def dummy_request():
    """Create a mock Request with configurable client IP and headers."""
    req = MagicMock()
    req.client.host = "192.168.1.50"  # Default in campus subnet 192.168.0.0/16
    req.headers.get = lambda h, d=None: None
    return req


@pytest.fixture
def mock_permission_checker():
    """Create a mock PermissionChecker returning True."""
    checker = MagicMock()
    checker.check_permission = AsyncMock(return_value=True)
    return checker


@pytest.mark.asyncio
async def test_check_control_work_access_happy_path(
    dummy_request, mock_permission_checker
):
    """Verify 200 OK / no exception raised when all ReBAC and ABAC checks pass with lesson object."""
    now = datetime.now(UTC)
    lesson = DummyLesson(
        start_time=now - timedelta(minutes=10),
        end_time=now + timedelta(minutes=50),
    )
    user_id = uuid.uuid4()

    await check_control_work_access(
        request=dummy_request,
        user_id=user_id,
        lesson=lesson,
        permission_checker=mock_permission_checker,
    )

    mock_permission_checker.check_permission.assert_awaited_once_with(
        resource_type="control_work",
        resource_id=str(lesson.id),
        permission="submit",
        user_id=str(user_id),
    )


@pytest.mark.asyncio
async def test_check_control_work_access_explicit_params_happy_path(
    dummy_request, mock_permission_checker
):
    """Verify 200 OK with explicit (resource_type, resource_id, lesson_start, lesson_end) arguments."""
    now = datetime.now(UTC)
    start_time = now - timedelta(minutes=10)
    end_time = now + timedelta(minutes=50)
    user_id = str(uuid.uuid4())
    resource_id = "cw-999"

    await check_control_work_access(
        request=dummy_request,
        user_id=user_id,
        resource_type="control_work",
        resource_id=resource_id,
        lesson_start=start_time,
        lesson_end=end_time,
        permission_checker=mock_permission_checker,
    )

    mock_permission_checker.check_permission.assert_awaited_once_with(
        resource_type="control_work",
        resource_id=resource_id,
        permission="submit",
        user_id=user_id,
    )


@pytest.mark.asyncio
async def test_check_control_work_access_accepts_positional_lesson_and_checker(
    dummy_request,
):
    """Resolve the documented positional lesson/checker compatibility form."""
    now = datetime.now(UTC)
    lesson = DummyLesson(
        start_time=now - timedelta(minutes=10),
        end_time=now + timedelta(minutes=50),
    )
    checker = PermissionChecker(MagicMock())
    checker.check_permission = AsyncMock(return_value=True)
    user_id = uuid.uuid4()

    await check_control_work_access(
        dummy_request,
        user_id,
        lesson,
        checker,
    )

    checker.check_permission.assert_awaited_once_with(
        resource_type="control_work",
        resource_id=str(lesson.id),
        permission="submit",
        user_id=str(user_id),
    )

    checker.check_permission.reset_mock()
    await check_control_work_access(
        dummy_request,
        user_id,
        lesson,
        "explicit-resource-id",
        permission_checker=checker,
    )
    checker.check_permission.assert_awaited_once_with(
        resource_type="control_work",
        resource_id=str(lesson.id),
        permission="submit",
        user_id=str(user_id),
    )


@pytest.mark.asyncio
async def test_check_control_work_access_allows_context_without_rebac_checker(
    dummy_request,
):
    """Continue with ABAC-only checks when no optional ReBAC checker is configured."""
    now = datetime.now(UTC)
    lesson = DummyLesson(
        start_time=now - timedelta(minutes=10),
        end_time=now + timedelta(minutes=50),
    )

    await check_control_work_access(
        request=dummy_request,
        user_id=uuid.uuid4(),
        lesson=lesson,
        permission_checker=None,
    )


@pytest.mark.asyncio
async def test_check_control_work_access_untrusted_cidr(
    dummy_request, mock_permission_checker
):
    """Verify HTTP 403 when client IP is outside campus subnets."""
    dummy_request.client.host = "203.0.113.195"  # Untrusted external IP
    now = datetime.now(UTC)
    lesson = DummyLesson(
        start_time=now - timedelta(minutes=10),
        end_time=now + timedelta(minutes=50),
    )

    with patch("app.auth.abac.record_abac_access_denied") as mock_record:
        with pytest.raises(HTTPException) as exc_info:
            await check_control_work_access(
                request=dummy_request,
                user_id=uuid.uuid4(),
                lesson=lesson,
                permission_checker=mock_permission_checker,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert (
            "outside scheduled time window or untrusted network"
            in exc_info.value.detail
        )
        mock_record.assert_called_once_with(rule="subnet")


@pytest.mark.asyncio
async def test_check_control_work_access_before_schedule_start(
    dummy_request, mock_permission_checker
):
    """Verify HTTP 403 when request is made before schedule start_time."""
    now = datetime.now(UTC)
    lesson = DummyLesson(
        start_time=now + timedelta(minutes=15),  # Starts in 15 minutes
        end_time=now + timedelta(minutes=75),
    )

    with patch("app.auth.abac.record_abac_access_denied") as mock_record:
        with pytest.raises(HTTPException) as exc_info:
            await check_control_work_access(
                request=dummy_request,
                user_id=uuid.uuid4(),
                lesson=lesson,
                permission_checker=mock_permission_checker,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        mock_record.assert_called_once_with(rule="schedule")


@pytest.mark.asyncio
async def test_check_control_work_access_after_schedule_end_plus_grace(
    dummy_request, mock_permission_checker
):
    """Verify HTTP 403 when request is made after end_time + grace_minutes."""
    now = datetime.now(UTC)
    grace = getattr(settings.security, "control_work_grace_minutes", 15)
    lesson = DummyLesson(
        start_time=now - timedelta(minutes=120),
        end_time=now - timedelta(minutes=grace + 5),  # 5 minutes past grace window
    )

    with patch("app.auth.abac.record_abac_access_denied") as mock_record:
        with pytest.raises(HTTPException) as exc_info:
            await check_control_work_access(
                request=dummy_request,
                user_id=uuid.uuid4(),
                lesson=lesson,
                permission_checker=mock_permission_checker,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        mock_record.assert_called_once_with(rule="schedule")


@pytest.mark.asyncio
async def test_check_control_work_access_within_grace_period(
    dummy_request, mock_permission_checker
):
    """Verify access allowed when request is made after end_time but within grace_minutes."""
    now = datetime.now(UTC)
    lesson = DummyLesson(
        start_time=now - timedelta(minutes=60),
        end_time=now - timedelta(minutes=5),  # Ended 5 min ago, default grace is 15 min
    )

    await check_control_work_access(
        request=dummy_request,
        user_id=uuid.uuid4(),
        lesson=lesson,
        permission_checker=mock_permission_checker,
    )


@pytest.mark.asyncio
async def test_check_control_work_access_rebac_denied(dummy_request):
    """Verify HTTP 403 when SpiceDB ReBAC check returns False."""
    now = datetime.now(UTC)
    lesson = DummyLesson(
        start_time=now - timedelta(minutes=10),
        end_time=now + timedelta(minutes=50),
    )
    checker = MagicMock()
    checker.check_permission = AsyncMock(return_value=False)

    with patch("app.auth.abac.record_abac_access_denied") as mock_record:
        with pytest.raises(HTTPException) as exc_info:
            await check_control_work_access(
                request=dummy_request,
                user_id=uuid.uuid4(),
                lesson=lesson,
                permission_checker=checker,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        mock_record.assert_called_once_with(rule="rebac")


@pytest.mark.asyncio
async def test_check_control_work_access_spicedb_unavailable(dummy_request):
    """Verify HTTP 403 (fail closed) when SpiceDB raises SpiceDBUnavailableError."""
    now = datetime.now(UTC)
    lesson = DummyLesson(
        start_time=now - timedelta(minutes=10),
        end_time=now + timedelta(minutes=50),
    )
    checker = MagicMock()
    checker.check_permission = AsyncMock(
        side_effect=SpiceDBUnavailableError("SpiceDB down")
    )

    with patch("app.auth.abac.record_abac_access_denied") as mock_record:
        with pytest.raises(HTTPException) as exc_info:
            await check_control_work_access(
                request=dummy_request,
                user_id=uuid.uuid4(),
                lesson=lesson,
                permission_checker=checker,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        mock_record.assert_called_once_with(rule="rebac")


@pytest.mark.asyncio
async def test_check_control_work_access_x_forwarded_for_trusted_proxy(
    mock_permission_checker, monkeypatch
):
    """Verify client IP extraction from X-Forwarded-For when client host is a trusted proxy."""
    monkeypatch.setattr(settings, "trusted_proxies_list", ["10.0.0.1"])
    request = MagicMock()
    request.client.host = "10.0.0.1"  # Trusted proxy host
    request.headers.get = lambda header, default=None: {
        "X-Forwarded-For": "10.1.2.3, 10.0.0.1",  # 10.1.2.3 is in 10.0.0.0/8
    }.get(header)

    now = datetime.now(UTC)
    lesson = DummyLesson(
        start_time=now - timedelta(minutes=10),
        end_time=now + timedelta(minutes=50),
    )

    await check_control_work_access(
        request=request,
        user_id=uuid.uuid4(),
        lesson=lesson,
        permission_checker=mock_permission_checker,
    )


@pytest.mark.asyncio
async def test_context_aware_access_guard_custom_configuration(
    dummy_request, mock_permission_checker
):
    """Verify ContextAwareAccessGuard with custom subnets and grace period."""
    guard = ContextAwareAccessGuard(
        permission_checker=mock_permission_checker,
        campus_subnets=["172.16.0.0/12"],
        grace_minutes=30,
    )
    assert guard.campus_subnets == ["172.16.0.0/12"]
    assert guard.grace_minutes == 30

    dummy_request.client.host = "172.16.5.10"
    now = datetime.now(UTC)
    # Ended 20 minutes ago (within custom 30 min grace)
    lesson = DummyLesson(
        start_time=now - timedelta(minutes=60),
        end_time=now - timedelta(minutes=20),
    )

    await guard.check_control_work_access(
        request=dummy_request,
        user_id=uuid.uuid4(),
        lesson=lesson,
    )


@pytest.mark.asyncio
async def test_check_control_work_access_missing_timing_raises_value_error(
    dummy_request, mock_permission_checker
):
    """Verify ValueError is raised if neither lesson nor lesson_start/end times are provided."""
    with pytest.raises(ValueError, match="Lesson start and end times must be provided"):
        await check_control_work_access(
            request=dummy_request,
            user_id=uuid.uuid4(),
            resource_type="control_work",
            resource_id="cw-1",
            permission_checker=mock_permission_checker,
        )


@pytest.mark.asyncio
async def test_check_control_work_access_logging_warnings(
    dummy_request, mock_permission_checker
):
    """Verify OTEL structlog warning is logged on access denial."""
    dummy_request.client.host = "203.0.113.10"
    now = datetime.now(UTC)
    lesson = DummyLesson(
        start_time=now - timedelta(minutes=10), end_time=now + timedelta(minutes=50)
    )

    with patch("app.auth.abac.logger") as mock_logger:
        with pytest.raises(HTTPException):
            await check_control_work_access(
                request=dummy_request,
                user_id=uuid.uuid4(),
                lesson=lesson,
                permission_checker=mock_permission_checker,
            )

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "outside campus subnets" in call_args[0][0]
