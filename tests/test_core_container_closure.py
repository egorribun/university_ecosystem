from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace

_MISSING = object()
_STUBBED_MODULE_NAMES = (
    "app.core.container",
    "app.core.database",
    "app.deps.cache",
    "app.services.audit_service",
    "app.services.auth_service",
    "app.services.event_service",
    "app.services.group_service",
    "app.services.news_service",
    "app.services.notification_service",
    "app.services.user_service",
    "app.services.vector_service",
    "app.services.user",
    "app.services.user.compliance_service",
    "app.services.user.media_service",
    "app.services.user.profile_service",
    "app.services.user.analytics_service",
    "app.cqrs.queries",
    "app.repositories.schedule_repository",
    "app.repositories.unit_of_work",
)
_ORIGINAL_MODULES = {
    name: sys.modules.get(name, _MISSING) for name in _STUBBED_MODULE_NAMES
}


def _class(name: str) -> type:
    return type(
        name,
        (),
        {"__init__": lambda self, *args, **kwargs: self.__dict__.update(kwargs)},
    )


def _install_stubs() -> None:
    database = ModuleType("app.core.database")
    database.get_db = lambda: None
    database.get_read_db = lambda: None
    sys.modules["app.core.database"] = database

    cache = ModuleType("app.deps.cache")
    cache.BaseCache = _class("BaseCache")
    cache.get_cache = lambda: None
    sys.modules["app.deps.cache"] = cache

    audit = ModuleType("app.services.audit_service")
    audit.AuditService = _class("AuditService")
    audit.SecureAuditService = _class("SecureAuditService")
    audit.get_secure_audit_service = lambda: audit.SecureAuditService()
    sys.modules["app.services.audit_service"] = audit

    for module_name, class_name in (
        ("app.services.auth_service", "AuthService"),
        ("app.services.event_service", "EventService"),
        ("app.services.group_service", "GroupService"),
        ("app.services.news_service", "NewsService"),
        ("app.services.notification_service", "NotificationService"),
        ("app.services.user_service", "UserService"),
        ("app.services.vector_service", "VectorService"),
    ):
        module = ModuleType(module_name)
        setattr(module, class_name, _class(class_name))
        sys.modules[module_name] = module

    user_package = ModuleType("app.services.user")
    user_package.__path__ = []
    sys.modules["app.services.user"] = user_package
    for module_name, class_name in (
        ("app.services.user.compliance_service", "UserComplianceService"),
        ("app.services.user.media_service", "UserMediaService"),
        ("app.services.user.profile_service", "UserProfileService"),
    ):
        module = ModuleType(module_name)
        setattr(module, class_name, _class(class_name))
        sys.modules[module_name] = module

    analytics = ModuleType("app.services.user.analytics_service")
    analytics.UserAnalyticsService = _class("UserAnalyticsService")
    sys.modules["app.services.user.analytics_service"] = analytics

    queries = ModuleType("app.cqrs.queries")
    queries.GetScheduleHandler = _class("GetScheduleHandler")
    queries.GetStatsHandler = _class("GetStatsHandler")
    sys.modules["app.cqrs.queries"] = queries

    schedule_repository = ModuleType("app.repositories.schedule_repository")
    schedule_repository.GroupRepository = _class("GroupRepository")
    sys.modules["app.repositories.schedule_repository"] = schedule_repository

    unit_of_work = ModuleType("app.repositories.unit_of_work")
    unit_of_work.uow_from_session = lambda db: SimpleNamespace(
        auth="auth", users="users", sessions="sessions"
    )
    sys.modules["app.repositories.unit_of_work"] = unit_of_work


_install_stubs()
container = importlib.import_module("app.core.container")

# This module replaces import dependencies only while importing the factory
# module.  Leaving the stubs in ``sys.modules`` poisons later closure tests
# that need the real CQRS modules (and makes collection order observable).
for _name, _original in _ORIGINAL_MODULES.items():
    if _original is _MISSING:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _original


def test_simple_factories_return_expected_types():
    assert isinstance(container.get_audit_service(), container.AuditService)
    assert isinstance(
        container.get_secure_audit_service_dep(), container.SecureAuditService
    )
    assert isinstance(
        container.get_notification_service(db="db"), container.NotificationService
    )
    assert isinstance(container.get_vector_service(db="db"), container.VectorService)


def test_service_factories_wire_dependencies(monkeypatch):
    monkeypatch.setattr(
        "app.repositories.unit_of_work.uow_from_session",
        lambda db: SimpleNamespace(
            auth="auth",
            users="users",
            sessions="sessions",
            events="events",
            news="news",
        ),
    )
    audit = object()
    notifications = object()
    vector = object()

    group = container.get_group_service(db="db")
    assert group.db == "db"
    assert group.repo.__class__.__name__ == "GroupRepository"

    user = container.get_user_service(db="db", audit=audit, notifications=notifications)
    assert user.uow.auth == "auth"
    assert user.audit is audit
    assert user.notifications is notifications

    profile = container.get_user_profile_service(
        db="db", audit=audit, notifications=notifications
    )
    assert profile.uow.users == "users"

    compliance = container.get_user_compliance_service(db="db", audit=audit)
    assert compliance.uow.sessions == "sessions"

    media = container.get_user_media_service(db="db")
    assert media.uow.users == "users"

    event = container.get_event_service(db="db", vector_service=vector)
    assert event.uow.auth == "auth"
    assert event.vector_service is vector

    news = container.get_news_service(db="db", vector_service=vector)
    assert news.uow.auth == "auth"
    assert news.vector_service is vector


def test_schedule_stats_and_auth_factories(monkeypatch):
    monkeypatch.setattr(
        "app.repositories.unit_of_work.uow_from_session",
        lambda db: SimpleNamespace(
            auth="auth",
            users="users",
            sessions="sessions",
            events="events",
            news="news",
        ),
    )
    schedule = container.get_schedule_handler(db="write-db", cache="cache")
    read_schedule = container.get_read_schedule_handler(db="read-db", cache="cache")
    assert schedule.db == "write-db"
    assert read_schedule.db == "read-db"

    analytics = container.get_user_analytics_service(db="db")
    stats = container.get_stats_handler(
        db="write-db", cache="cache", analytics_service=analytics
    )
    read_stats = container.get_read_stats_handler(
        db="read-db", cache="cache", analytics_service=analytics
    )
    assert stats.db == "write-db"
    assert read_stats.db == "read-db"
    assert stats.analytics_service is analytics

    auth = container.get_auth_service(db="db", audit="audit")
    assert auth.auth_repo == "auth"
    assert auth.user_repo == "users"
    assert auth.session_repo == "sessions"
    assert auth.audit == "audit"
