from __future__ import annotations

import logging

from app.core.logging import get_logger
from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from app.services.search import SearchService

_logger = get_logger(__name__)


class SearchProvider(Provider):
    @provide(scope=Scope.APP)
    async def search_service(self) -> AsyncIterator[SearchService]:
        from app.core.config import settings

        hosts: str = getattr(settings, "elasticsearch_url", "http://localhost:9200")
        user: str = getattr(settings, "elasticsearch_user", "elastic")
        password: str = getattr(settings, "elasticsearch_password", "")
        http_auth: tuple[str, str] | None = (user, password) if password else None

        svc = SearchService(hosts=hosts, http_auth=http_auth)
        _logger.info("Dishka: SearchService created (Scope.APP)")
        try:
            yield svc
        finally:
            await svc.close()
            _logger.info("Dishka: SearchService closed")
