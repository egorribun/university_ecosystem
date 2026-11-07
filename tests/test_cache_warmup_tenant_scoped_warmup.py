"""Startup warmup must skip the news version refresh inside a scoped request context."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.tenant import (
    bypass_rls_ctx,
    set_bypass_rls,
    set_current_tenant,
    tenant_id_ctx,
)
from app.services import cache_warmup


async def _run_warm_cache() -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    cache = MagicMock()
    cache.enabled = True
    db = AsyncMock()
    warm_news = AsyncMock()
    # news_cache_version is a frozen dataclass, so the whole module-level
    # collaborator is replaced rather than its method.
    news_version = MagicMock()
    news_version.prepare_warmup = AsyncMock()
    with (
        patch("app.services.cache_warmup.settings") as settings_mock,
        patch("app.services.cache_warmup.get_cache", return_value=cache),
        patch("app.services.cache_warmup.async_session") as session_factory,
        patch("app.services.cache_warmup._warm_schedule", AsyncMock()),
        patch("app.services.cache_warmup._warm_stats", AsyncMock()),
        patch("app.services.cache_warmup._warm_news", warm_news),
        patch("app.services.cache_warmup.news_cache_version", news_version),
    ):
        settings_mock.cache_warmup_enabled = True
        session_factory.return_value.__aenter__.return_value = db
        await cache_warmup.warm_cache()
    return db, warm_news, news_version.prepare_warmup


@pytest.mark.asyncio
async def test_unscoped_warmup_refreshes_the_news_version_first() -> None:
    db, warm_news, prepare_warmup = await _run_warm_cache()

    prepare_warmup.assert_awaited_once()
    db.rollback.assert_awaited_once()
    warm_news.assert_awaited_once()


@pytest.mark.asyncio
async def test_tenant_scoped_warmup_does_not_refresh_the_news_version() -> None:
    token = set_current_tenant(uuid.uuid4())
    try:
        db, warm_news, prepare_warmup = await _run_warm_cache()
    finally:
        tenant_id_ctx.reset(token)

    prepare_warmup.assert_not_awaited()
    db.rollback.assert_awaited_once()
    warm_news.assert_awaited_once()


@pytest.mark.asyncio
async def test_rls_bypass_warmup_does_not_refresh_the_news_version() -> None:
    token = set_bypass_rls(True)
    try:
        db, warm_news, prepare_warmup = await _run_warm_cache()
    finally:
        bypass_rls_ctx.reset(token)

    prepare_warmup.assert_not_awaited()
    db.rollback.assert_awaited_once()
    warm_news.assert_awaited_once()
