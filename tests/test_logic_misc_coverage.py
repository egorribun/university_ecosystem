"""Coverage boost v3 — targets 0% and low-coverage pure-logic modules.

Covers: graphql/extensions, graphql/permissions, user_stats_repository,
data_access, cache_invalidation, privacy_cleanup, schedule_service,
notifications/cleanup, graphql_token_validator, schedule_optimizer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Pin all tests in this file to one xdist worker.
# These tests are pure-logic (no DB fixtures) but share a session-scope
# event loop. Running them across workers with --dist=loadgroup causes
# cross-worker loop contention and deadlocks on Python 3.14 / Linux CI.
pytestmark = pytest.mark.xdist_group("logic_misc_coverage")

# ---------------------------------------------------------------------------
# 1. graphql/extensions.py — QueryCostExtension + _CostVisitor
# ---------------------------------------------------------------------------


def test_cost_visitor_scalar_field():
    from graphql.language.ast import FieldNode, NameNode

    from app.graphql.extensions import _FIELD_COST, _LIST_FIELD_COST, _CostVisitor

    visitor = _CostVisitor()
    scalar_node = MagicMock(spec=FieldNode)
    scalar_node.name = MagicMock(spec=NameNode)
    scalar_node.name.value = "id"
    visitor.enter_field(scalar_node)
    assert visitor.cost == _FIELD_COST

    list_node = MagicMock(spec=FieldNode)
    list_node.name = MagicMock(spec=NameNode)
    list_node.name.value = "messages"
    visitor.enter_field(list_node)
    assert visitor.cost == _FIELD_COST + _LIST_FIELD_COST


def test_cost_visitor_all_list_fields():
    from app.graphql.extensions import _LIST_FIELD_COST, _LIST_FIELD_NAMES, _CostVisitor

    visitor = _CostVisitor()
    for name in list(_LIST_FIELD_NAMES)[:3]:
        node = MagicMock()
        node.name.value = name
        visitor.enter_field(node)
    assert visitor.cost == 3 * _LIST_FIELD_COST


@pytest.mark.asyncio
async def test_query_cost_extension_low_cost():
    from app.graphql.extensions import QueryCostExtension, _CostVisitor

    ext = object.__new__(QueryCostExtension)
    ext.execution_context = MagicMock()
    ext.execution_context.errors = None
    mock_doc = MagicMock()
    ext.execution_context.graphql_document = mock_doc
    ext.execution_context.context = MagicMock()
    ext.execution_context.context.current_user = None

    visitor_instance = MagicMock(spec=_CostVisitor)
    visitor_instance.cost = 10  # under max

    with (
        patch("app.graphql.extensions.visit"),
        patch("app.graphql.extensions._CostVisitor", return_value=visitor_instance),
    ):
        gen = ext.on_validate()
        await gen.__anext__()
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass


@pytest.mark.asyncio
async def test_query_cost_extension_high_cost():
    from graphql import GraphQLError

    from app.graphql.extensions import _MAX_QUERY_COST, QueryCostExtension, _CostVisitor

    ext = object.__new__(QueryCostExtension)
    ext.execution_context = MagicMock()
    ext.execution_context.pre_execution_errors = None
    mock_doc = MagicMock()
    ext.execution_context.graphql_document = mock_doc
    ext.execution_context.context = MagicMock()
    ext.execution_context.context.current_user = None

    visitor_instance = MagicMock(spec=_CostVisitor)
    visitor_instance.cost = _MAX_QUERY_COST + 1

    with (
        patch("app.graphql.extensions.visit"),
        patch("app.graphql.extensions._CostVisitor", return_value=visitor_instance),
    ):
        gen = ext.on_validate()
        await gen.__anext__()
        with pytest.raises(GraphQLError):
            await gen.__anext__()


@pytest.mark.asyncio
async def test_query_cost_extension_prior_errors():
    from app.graphql.extensions import QueryCostExtension

    ext = object.__new__(QueryCostExtension)
    ext.execution_context = MagicMock()
    ext.execution_context.errors = ["some error"]

    gen = ext.on_validate()
    await gen.__anext__()
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass


@pytest.mark.asyncio
async def test_query_cost_extension_no_document():
    from app.graphql.extensions import QueryCostExtension

    ext = object.__new__(QueryCostExtension)
    # execution_context has no .errors, no .graphql_document
    ctx = MagicMock(spec=[])
    ext.execution_context = ctx

    gen = ext.on_validate()
    await gen.__anext__()
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass


# ---------------------------------------------------------------------------
# 2. graphql/permissions.py — IsAuthenticated, IsAdmin
# ---------------------------------------------------------------------------


def test_is_authenticated_true():
    from app.graphql.permissions import IsAuthenticated

    perm = IsAuthenticated()
    info = MagicMock()
    info.context.is_authenticated = True
    assert perm.has_permission(None, info) is True


def test_is_authenticated_false():
    from app.graphql.permissions import IsAuthenticated

    perm = IsAuthenticated()
    info = MagicMock()
    info.context.is_authenticated = False
    assert perm.has_permission(None, info) is False


@pytest.mark.asyncio
async def test_is_admin_not_authenticated():
    from app.graphql.permissions import IsAdmin

    perm = IsAdmin()
    info = MagicMock()
    info.context.is_authenticated = False
    info.context.current_user = None
    result = await perm.has_permission(None, info)
    assert result is False


@pytest.mark.asyncio
async def test_is_admin_no_checker():
    from app.graphql.permissions import IsAdmin

    perm = IsAdmin()
    info = MagicMock()
    info.context.is_authenticated = True
    info.context.current_user = MagicMock(id=uuid.uuid4())
    # Remove checker attribute
    del info.context.checker
    result = await perm.has_permission(None, info)
    assert result is False


@pytest.mark.asyncio
async def test_is_admin_spicedb_unavailable():
    from app.auth.rbac import SpiceDBUnavailableError
    from app.graphql.permissions import IsAdmin

    perm = IsAdmin()
    info = MagicMock()
    info.context.is_authenticated = True
    info.context.current_user = MagicMock(id=uuid.uuid4())
    checker = AsyncMock()
    checker.check_admin = AsyncMock(side_effect=SpiceDBUnavailableError("down"))
    info.context.checker = checker
    result = await perm.has_permission(None, info)
    assert result is False


@pytest.mark.asyncio
async def test_is_admin_unexpected_exception():
    from app.graphql.permissions import IsAdmin

    perm = IsAdmin()
    info = MagicMock()
    info.context.is_authenticated = True
    info.context.current_user = MagicMock(id=uuid.uuid4())
    checker = AsyncMock()
    checker.check_admin = AsyncMock(side_effect=RuntimeError("boom"))
    info.context.checker = checker
    result = await perm.has_permission(None, info)
    assert result is False


@pytest.mark.asyncio
async def test_is_admin_success():
    from app.graphql.permissions import IsAdmin

    perm = IsAdmin()
    info = MagicMock()
    info.context.is_authenticated = True
    info.context.current_user = MagicMock(id=uuid.uuid4())
    checker = AsyncMock()
    checker.check_admin = AsyncMock(return_value=True)
    info.context.checker = checker
    result = await perm.has_permission(None, info)
    assert result is True


# ---------------------------------------------------------------------------
# 3. repositories/user_stats_repository.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_stats_repository_get_attendance_stats_raw():
    from app.repositories.user_stats_repository import UserStatsRepository

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    repo = UserStatsRepository(mock_db)
    now = datetime.now(UTC)
    rows = await repo.get_attendance_stats_raw(
        user_id=uuid.uuid4(),
        window_start=now - timedelta(days=30),
        previous_start=now - timedelta(days=60),
        now=now,
    )
    assert rows == []
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_user_stats_repository_get_grade_notifications():
    from app.repositories.user_stats_repository import UserStatsRepository

    mock_db = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    mock_db.execute = AsyncMock(return_value=result_mock)

    repo = UserStatsRepository(mock_db)
    now = datetime.now(UTC)
    rows = await repo.get_grade_notifications(
        user_id=uuid.uuid4(),
        start_date=now - timedelta(days=30),
        end_date=now,
    )
    assert rows == []


@pytest.mark.asyncio
async def test_user_stats_repository_get_participation_stats_raw():
    from app.repositories.user_stats_repository import UserStatsRepository

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    repo = UserStatsRepository(mock_db)
    now = datetime.now(UTC)
    rows = await repo.get_participation_stats_raw(
        user_id=uuid.uuid4(),
        window_start=now - timedelta(days=30),
        now=now,
    )
    assert rows == []


def test_get_user_stats_repository_factory():
    from app.repositories.user_stats_repository import (
        UserStatsRepository,
        get_user_stats_repository,
    )

    mock_db = MagicMock()
    repo = get_user_stats_repository(mock_db)
    assert isinstance(repo, UserStatsRepository)


# ---------------------------------------------------------------------------
# 4. services/data_access.py
# ---------------------------------------------------------------------------


def test_normalize_time_none():
    from app.services.data_access import _normalize_time

    assert _normalize_time(None) is None


def test_normalize_time_naive():
    from app.services.data_access import _normalize_time

    naive = datetime(2026, 1, 1, 12, 0, 0)
    result = _normalize_time(naive)
    assert result is not None
    assert result.tzinfo is not None


def test_normalize_time_aware():
    from app.services.data_access import _normalize_time

    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    result = _normalize_time(aware)
    assert result.tzinfo is not None


def test_serialize_access_logs_csv_empty():
    from app.services.data_access import serialize_access_logs_csv

    csv_out = serialize_access_logs_csv([])
    assert "created_at" in csv_out


def test_serialize_access_logs_csv_with_entries():
    from app.schemas.dtos.audit import DataAccessLogDTO
    from app.services.data_access import serialize_access_logs_csv

    entry = DataAccessLogDTO(
        id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        subject_user_id=uuid.uuid4(),
        resource_type="user",
        resource_id="123",
        action="read",
        ip_address="127.0.0.1",
        user_agent="pytest",
        context={"key": "value"},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        signature="abc123",
    )
    csv_out = serialize_access_logs_csv([entry])
    assert "user" in csv_out
    assert "read" in csv_out


@pytest.mark.asyncio
async def test_cleanup_access_logs_zero_retention():
    from app.services.data_access import cleanup_access_logs

    result = await cleanup_access_logs(db=AsyncMock(), retention_days=0)
    assert result == 0


@pytest.mark.asyncio
async def test_cleanup_access_logs_with_db():
    from app.services.data_access import cleanup_access_logs

    mock_db = AsyncMock()
    mock_repo = MagicMock()
    mock_repo.prune_logs = AsyncMock(return_value=5)

    with patch("app.services.data_access.AuditRepository", return_value=mock_repo):
        result = await cleanup_access_logs(db=mock_db, retention_days=30)
    assert result == 5


@pytest.mark.asyncio
async def test_export_access_logs_no_filters():
    from app.services.data_access import export_access_logs

    mock_db = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    mock_db.execute = AsyncMock(return_value=result_mock)

    with patch("app.services.data_access.AuditRepository") as MockRepo:
        mock_repo = MagicMock()
        mock_repo._to_dto = MagicMock(return_value=MagicMock())
        MockRepo.return_value = mock_repo
        result = await export_access_logs(mock_db)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_export_access_logs_with_all_filters():
    from app.services.data_access import export_access_logs

    mock_db = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    mock_db.execute = AsyncMock(return_value=result_mock)

    with patch("app.services.data_access.AuditRepository") as MockRepo:
        MockRepo.return_value = MagicMock(_to_dto=MagicMock())
        now = datetime.now(UTC)
        result = await export_access_logs(
            mock_db,
            start_at=now - timedelta(days=30),
            end_at=now,
            actor_user_id=1,
            subject_user_id=2,
        )
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# 5. services/cache_invalidation.py
# ---------------------------------------------------------------------------


def test_cache_tag_enum_values():
    from app.services.cache_invalidation import CacheTag

    assert CacheTag.SCHEDULE == "tag:schedule"
    assert CacheTag.USER == "tag:user"
    assert CacheTag.EVENT == "tag:event"
    assert CacheTag.NEWS == "tag:news"
    assert CacheTag.GROUPS == "tag:groups"
    assert CacheTag.NOTIFICATIONS == "tag:notifications"


def test_get_tags_for_key_schedule():
    from app.services.cache_invalidation import CacheTag, get_tags_for_key

    tags = get_tags_for_key("schedule:group:123")
    assert CacheTag.SCHEDULE in tags


def test_get_tags_for_key_user():
    from app.services.cache_invalidation import CacheTag, get_tags_for_key

    tags = get_tags_for_key("user:profile:abc")
    assert CacheTag.USER in tags


def test_get_tags_for_key_no_match():
    from app.services.cache_invalidation import get_tags_for_key

    tags = get_tags_for_key("some:random:key")
    assert tags == []


def test_get_tags_for_key_event():
    from app.services.cache_invalidation import CacheTag, get_tags_for_key

    tags = get_tags_for_key("event:detail:456")
    assert CacheTag.EVENT in tags


def test_get_tags_for_key_news():
    from app.services.cache_invalidation import CacheTag, get_tags_for_key

    tags = get_tags_for_key("news:latest")
    assert CacheTag.NEWS in tags


def test_get_tags_for_key_groups():
    from app.services.cache_invalidation import CacheTag, get_tags_for_key

    tags = get_tags_for_key("groups:list:all")
    assert CacheTag.GROUPS in tags


# ---------------------------------------------------------------------------
# 6. services/privacy_cleanup.py
# ---------------------------------------------------------------------------


def test_privacy_cleanup_config_defaults():
    from app.services.privacy_cleanup import PrivacyCleanupConfig

    cfg = PrivacyCleanupConfig()
    assert cfg.session_retention_days == 90
    assert cfg.mfa_retention_days == 30
    assert cfg.audit_log_retention_days == 180
    assert cfg.normalized_interval() >= 60


def test_privacy_cleanup_config_minimum_interval():
    from app.services.privacy_cleanup import PrivacyCleanupConfig

    cfg = PrivacyCleanupConfig(interval_seconds=0)
    assert cfg.normalized_interval() == 60


def test_cutoff_basic():
    from app.services.privacy_cleanup import _cutoff

    cutoff = _cutoff(30)
    assert cutoff < datetime.now(UTC)


def test_cutoff_zero():
    from app.services.privacy_cleanup import _cutoff

    cutoff0 = _cutoff(0)
    assert cutoff0 <= datetime.now(UTC)


@pytest.mark.asyncio
async def test_cleanup_sessions_mock():
    from app.services.privacy_cleanup import _cleanup_sessions

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 3
    mock_db.execute = AsyncMock(return_value=mock_result)

    count = await _cleanup_sessions(mock_db, retention_days=30)
    assert count == 3


@pytest.mark.asyncio
async def test_cleanup_mfa_challenges_mock():
    from app.services.privacy_cleanup import _cleanup_mfa_challenges

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 1
    mock_db.execute = AsyncMock(return_value=mock_result)

    count = await _cleanup_mfa_challenges(mock_db, retention_days=30)
    assert count == 1


@pytest.mark.asyncio
async def test_cleanup_mfa_enrollments_mock():
    from app.services.privacy_cleanup import _cleanup_mfa_enrollments

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 0
    mock_db.execute = AsyncMock(return_value=mock_result)

    count = await _cleanup_mfa_enrollments(mock_db, retention_days=30)
    assert count == 0


@pytest.mark.asyncio
async def test_cleanup_failed_logins_mock():
    from app.services.privacy_cleanup import _cleanup_failed_logins

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 2
    mock_db.execute = AsyncMock(return_value=mock_result)

    count = await _cleanup_failed_logins(mock_db, retention_days=30)
    assert count == 2


@pytest.mark.asyncio
async def test_cleanup_privacy_artifacts_with_db():
    from app.services.privacy_cleanup import (
        PrivacyCleanupConfig,
        cleanup_privacy_artifacts,
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 0
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()

    cfg = PrivacyCleanupConfig()
    run_ctx = MagicMock()
    run_ctx.observe_deleted = MagicMock()
    run_ctx.__aenter__ = AsyncMock(return_value=run_ctx)
    run_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "app.services.privacy_cleanup.cleanup_access_logs",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch("app.services.privacy_cleanup._METRICS") as mock_metrics,
    ):
        mock_metrics.track_execution.return_value = run_ctx
        result = await cleanup_privacy_artifacts(db=mock_db, config=cfg)

    assert "sessions" in result
    assert "mfa_challenges" in result
    assert "mfa_enrollments" in result
    assert "failed_logins" in result
    assert "access_logs" in result


# ---------------------------------------------------------------------------
# 7. services/schedule_service.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_service_get_schedule():
    from app.services.schedule_service import ScheduleService

    mock_uow = MagicMock()
    mock_uow.schedules = AsyncMock()
    mock_uow.schedules.get_by_group = AsyncMock(return_value=[])
    mock_uow.groups = AsyncMock()

    svc = ScheduleService(mock_uow, MagicMock())
    result = await svc.get_schedule(uuid.uuid4())
    assert result == []


@pytest.mark.asyncio
async def test_schedule_service_get_by_id_none():
    from app.services.schedule_service import ScheduleService

    mock_uow = MagicMock()
    mock_uow.schedules = AsyncMock()
    mock_uow.schedules.get = AsyncMock(return_value=None)
    mock_uow.groups = AsyncMock()

    svc = ScheduleService(mock_uow, MagicMock())
    result = await svc.get_by_id(uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_schedule_service_delete_not_found():
    from app.services.schedule_service import ScheduleService

    mock_uow = MagicMock()
    mock_uow.schedules = AsyncMock()
    mock_uow.schedules.get = AsyncMock(return_value=None)
    mock_uow.groups = AsyncMock()

    svc = ScheduleService(mock_uow, MagicMock())
    result = await svc.delete_schedule(uuid.uuid4())
    assert result is False


@pytest.mark.asyncio
async def test_schedule_service_delete_success():
    from app.services.schedule_service import ScheduleService

    mock_uow = MagicMock()
    mock_uow.schedules = AsyncMock()
    mock_uow.schedules.get = AsyncMock(return_value=MagicMock())
    mock_uow.schedules.delete = AsyncMock()
    mock_uow.groups = AsyncMock()
    mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
    mock_uow.__aexit__ = AsyncMock(return_value=False)
    mock_uow.commit = AsyncMock()

    svc = ScheduleService(mock_uow, MagicMock())
    with patch("app.services.audit_service.get_secure_audit_service") as audit_factory:
        audit_factory.return_value.record_domain_event = AsyncMock()
        result = await svc.delete_schedule(uuid.uuid4())
    assert result is True


@pytest.mark.asyncio
async def test_schedule_service_update_not_found():
    from app.services.schedule_service import ScheduleService

    mock_uow = MagicMock()
    mock_uow.schedules = AsyncMock()
    mock_uow.schedules.get = AsyncMock(return_value=None)
    mock_uow.groups = AsyncMock()

    svc = ScheduleService(mock_uow, MagicMock())
    with pytest.raises(ValueError):
        await svc.update_schedule(uuid.uuid4(), MagicMock())


@pytest.mark.asyncio
async def test_schedule_service_list_groups():
    from app.services.schedule_service import ScheduleService

    mock_uow = MagicMock()
    mock_uow.schedules = AsyncMock()
    mock_uow.groups = AsyncMock()
    mock_uow.groups.list_groups = AsyncMock(return_value=[])

    svc = ScheduleService(mock_uow, MagicMock())
    result = await svc.list_groups()
    assert result == []


@pytest.mark.asyncio
async def test_schedule_service_create_group():
    from app.services.schedule_service import ScheduleService

    mock_group = MagicMock()
    mock_uow = MagicMock()
    mock_uow.schedules = AsyncMock()
    mock_uow.groups = AsyncMock()
    mock_uow.groups.create = AsyncMock(return_value=mock_group)
    mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
    mock_uow.__aexit__ = AsyncMock(return_value=False)
    mock_uow.commit = AsyncMock()

    svc = ScheduleService(mock_uow, MagicMock())
    result = await svc.create_group(MagicMock())
    assert result is mock_group


@pytest.mark.asyncio
async def test_schedule_service_create_with_conflict():
    from app.core.exceptions.domain import BusinessRuleViolation
    from app.services.schedule_service import ScheduleService

    mock_uow = MagicMock()
    mock_uow.schedules = AsyncMock()
    mock_uow.schedules.get_by_group = AsyncMock(return_value=[])
    mock_uow.schedules.get_by_teacher = AsyncMock(return_value=[])
    mock_uow.groups = AsyncMock()
    optimizer = MagicMock()
    optimizer.detect_conflicts = AsyncMock(return_value=[MagicMock()])

    svc = ScheduleService(mock_uow, optimizer)
    data = MagicMock()
    data.group_id = uuid.uuid4()
    data.teacher = "Dr. Test"
    data.weekday = "Monday"
    data.start_time = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    data.end_time = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    data.parity = "both"

    with pytest.raises(BusinessRuleViolation):
        await svc.create_schedule(data, locale="en")


@pytest.mark.asyncio
async def test_schedule_service_create_no_teacher():
    """create_schedule skips get_by_teacher when teacher is None/falsy."""
    from app.services.schedule_service import ScheduleService

    mock_uow = MagicMock()
    mock_uow.schedules = AsyncMock()
    mock_uow.schedules.get_by_group = AsyncMock(return_value=[])
    mock_uow.schedules.create = AsyncMock(return_value=MagicMock())
    mock_uow.groups = AsyncMock()
    mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
    mock_uow.__aexit__ = AsyncMock(return_value=False)
    mock_uow.commit = AsyncMock()
    optimizer = MagicMock()
    optimizer.detect_conflicts = AsyncMock(return_value=[])  # no conflicts

    svc = ScheduleService(mock_uow, optimizer)
    data = MagicMock()
    data.group_id = uuid.uuid4()
    data.teacher = None  # no teacher
    data.weekday = "Monday"
    data.start_time = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    data.end_time = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    data.parity = "both"

    with patch("app.services.audit_service.get_secure_audit_service") as audit_factory:
        audit_factory.return_value.record_domain_event = AsyncMock()
        result = await svc.create_schedule(data, locale="en")
    assert result is not None
    mock_uow.schedules.get_by_teacher.assert_not_called()


# ---------------------------------------------------------------------------
# 8. services/notifications/cleanup.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_stale_notifications_zero_retention():
    from app.services.notifications.cleanup import cleanup_stale_notifications

    result = await cleanup_stale_notifications(db=AsyncMock(), retention_days=0)
    assert result == (0, 0)


@pytest.mark.asyncio
async def test_cleanup_stale_notifications_negative():
    from app.services.notifications.cleanup import cleanup_stale_notifications

    result = await cleanup_stale_notifications(db=AsyncMock(), retention_days=-5)
    assert result == (0, 0)


@pytest.mark.asyncio
async def test_cleanup_stale_notifications_empty_db():
    from app.services.notifications.cleanup import cleanup_stale_notifications

    mock_db = AsyncMock()
    mock_scalars = AsyncMock()
    mock_scalars.all = MagicMock(return_value=[])
    mock_db.scalars = AsyncMock(return_value=mock_scalars)
    mock_db.commit = AsyncMock()

    result = await cleanup_stale_notifications(
        db=mock_db,
        retention_days=30,
        now=datetime.now(UTC),
    )
    assert result == (0, 0)


# ---------------------------------------------------------------------------
# 9. services/auth/graphql_token_validator.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graphql_token_validator_redis_revoked():
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    validator = GraphQLTokenValidator(MagicMock(), AsyncMock())
    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=1)

    with patch(
        "app.services.auth.graphql_token_validator.get_revocation_redis_client",
        new_callable=AsyncMock,
        return_value=mock_redis,
    ):
        result = await validator.validate(str(uuid.uuid4()), "revoked-jti")

    assert result is None


@pytest.mark.asyncio
async def test_graphql_token_validator_no_db_session():
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    validator = GraphQLTokenValidator(MagicMock(), mock_session)
    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=0)

    with patch(
        "app.services.auth.graphql_token_validator.get_revocation_redis_client",
        new_callable=AsyncMock,
        return_value=mock_redis,
    ):
        result = await validator.validate(str(uuid.uuid4()), "test-jti")

    assert result is None


def test_graphql_token_validator_check_expiry_expired():
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    validator = GraphQLTokenValidator(MagicMock(), AsyncMock())
    session = MagicMock()
    session.jti = "test-jti"
    session.expires_at = datetime(2020, 1, 1, tzinfo=UTC)
    assert validator._check_expiry(session) is False


def test_graphql_token_validator_check_expiry_valid():
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    validator = GraphQLTokenValidator(MagicMock(), AsyncMock())
    session = MagicMock()
    session.jti = "test-jti"
    session.expires_at = datetime(2099, 1, 1, tzinfo=UTC)
    assert validator._check_expiry(session) is True


def test_graphql_token_validator_check_expiry_naive():
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    validator = GraphQLTokenValidator(MagicMock(), AsyncMock())
    session = MagicMock()
    session.jti = "test-jti"
    session.expires_at = datetime(2020, 1, 1)  # naive, past
    assert validator._check_expiry(session) is False


@pytest.mark.asyncio
async def test_graphql_token_validator_load_user_invalid_uuid():
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    validator = GraphQLTokenValidator(MagicMock(), AsyncMock())
    result = await validator._load_user("not-a-uuid")
    assert result is None


@pytest.mark.asyncio
async def test_graphql_token_validator_fingerprint_no_hash():
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    validator = GraphQLTokenValidator(MagicMock(), AsyncMock())
    session = MagicMock()
    session.fingerprint_hash = None
    result = await validator._check_fingerprint(MagicMock(), session)
    assert result is True


@pytest.mark.asyncio
async def test_graphql_token_validator_redis_unavailable():
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    validator = GraphQLTokenValidator(MagicMock(), AsyncMock())
    with patch(
        "app.services.auth.graphql_token_validator.get_revocation_redis_client",
        new_callable=AsyncMock,
        side_effect=ConnectionError("Redis down"),
    ):
        result = await validator._redis_jti_check("some-jti")

    assert result is True  # Continue to the mandatory database revocation check.


@pytest.mark.asyncio
async def test_graphql_token_validator_load_db_session_db_error():
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=OSError("DB down"))
    validator = GraphQLTokenValidator(MagicMock(), mock_session)
    result = await validator._load_db_session("some-jti")
    assert result is None
