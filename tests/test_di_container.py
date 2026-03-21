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
