"""DI container smoke-test — MOD-W10-06.

Verifies that all critical APP-scoped services can be resolved from the Dishka
container without errors.  A failed resolve indicates a mis-registered provider
or a broken dependency chain.  These tests are intended to catch wiring mistakes
early (at CI time) rather than on the first production request.

Request-scoped services (ChatCommandService, ChatCreationService) require a live
DB session so they are NOT tested here — they are exercised by the API integration
tests (test_chat_api.py, etc.).
"""

from __future__ import annotations

import pytest

from app.core.di_provider import create_dishka_container
from app.deps.cache import BaseCache
from app.workers.outbox import OutboxWorker


@pytest.mark.asyncio
async def test_di_resolves_cache() -> None:
    """BaseCache (REQUEST-scoped) resolves without errors inside a request scope."""
    container = create_dishka_container()
    try:
        async with container() as request_container:
            cache = await request_container.get(BaseCache)
            assert cache is not None
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_di_resolves_outbox_worker() -> None:
    """OutboxWorker (APP-scoped) resolves without errors."""
    container = create_dishka_container()
    try:
        worker = await container.get(OutboxWorker)
        assert worker is not None
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_di_app_singletons_are_same_instance() -> None:
    """APP-scoped providers return the same instance on repeated get() calls."""
    container = create_dishka_container()
    try:
        worker_a = await container.get(OutboxWorker)
        worker_b = await container.get(OutboxWorker)
        assert worker_a is worker_b, "OutboxWorker must be a Scope.APP singleton"
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_read_component_resolves_query_services_against_the_replica() -> None:
    """BE-04: the read component expresses what the type system cannot.

    ``get_db`` and ``get_read_db`` both yield ``AsyncDatabaseSession``, so the
    container cannot distinguish a read service from a write one by type. The
    ``read`` component registers the same providers a second time over the
    replica session, which is what lets endpoints drop the legacy
    ``get_read_*`` factories.
    """
    from app.core.di.read_replica import READ_COMPONENT
    from app.core.protocols import AsyncDatabaseSession
    from app.services.news_service import NewsService

    container = create_dishka_container()
    try:
        async with container() as request_container:
            write_service = await request_container.get(NewsService)
            read_service = await request_container.get(
                NewsService, component=READ_COMPONENT
            )
            write_session = await request_container.get(AsyncDatabaseSession)
            read_session = await request_container.get(
                AsyncDatabaseSession, component=READ_COMPONENT
            )

            assert isinstance(read_service, NewsService)
            # Distinct objects, or the component would be decorative.
            assert read_service is not write_service
            assert read_session is not write_session
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_read_component_shares_app_singletons_instead_of_rebuilding_them() -> (
    None
):
    """Components do not fall back, so the bridges must re-expose, not rebuild.

    A second ``AuditService`` or cache inside the read component would be a
    silent duplicate: two audit sinks, two cache clients, one application.
    """
    from app.core.di.read_replica import READ_COMPONENT
    from app.services.audit_service import AuditService

    container = create_dishka_container()
    try:
        default_audit = await container.get(AuditService)
        read_audit = await container.get(AuditService, component=READ_COMPONENT)
        assert read_audit is default_audit

        async with container() as request_container:
            default_cache = await request_container.get(BaseCache)
            read_cache = await request_container.get(
                BaseCache, component=READ_COMPONENT
            )
            assert read_cache is default_cache
    finally:
        await container.close()
