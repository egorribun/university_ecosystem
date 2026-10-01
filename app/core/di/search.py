from __future__ import annotations

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from app.core.logging import get_logger
from app.services.search import SearchService

_logger = get_logger(__name__)


class SearchProvider(Provider):
    @provide(scope=Scope.APP)
    async def search_service(self) -> AsyncIterator[SearchService]:
        from app.services.search_indexer import build_search_service

        svc = build_search_service()
        _logger.info("Dishka: SearchService created (Scope.APP)")
        try:
            yield svc
        finally:
            await svc.close()
            _logger.info("Dishka: SearchService closed")
