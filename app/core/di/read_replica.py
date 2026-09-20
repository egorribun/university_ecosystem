"""Read-replica component for the Dishka container.

BE-04 groundwork. The legacy factories in ``app/api/deps/services.py`` expose
each query service twice -- ``get_news_service`` and ``get_read_news_service``
build the *same* class and differ only in which session they receive. The
container cannot express that distinction by type, because
``app/core/database.py`` yields the same ``AsyncDatabaseSession`` from both
``get_db`` and ``get_read_db``.

Dishka's answer is a component: the same providers registered a second time
under a name, resolving their own ``AsyncDatabaseSession`` from this module
while endpoints ask for ``Annotated[T, FromComponent(READ_COMPONENT)]``.

Components do not fall back to the default component, so every dependency a
re-registered provider needs must exist here too. APP-scoped singletons are
therefore *bridged* rather than rebuilt: each bridge below pulls the object out
of the default component and re-exposes the identical instance, so a read
service shares the application's audit service and cache instead of
constructing a second one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from dishka import DEFAULT_COMPONENT, FromComponent, Provider, Scope, provide

from app.core.protocols import AsyncDatabaseSession
from app.deps.cache import BaseCache
from app.services.audit_service import AuditService

READ_COMPONENT = "read"


class ReadReplicaProvider(Provider):
    """Bind the read-replica session and bridge the shared singletons."""

    component = READ_COMPONENT

    @provide(scope=Scope.REQUEST)
    async def read_db(self) -> AsyncIterator[AsyncDatabaseSession]:
        """Yield a session bound to the replica, falling back to the primary.

        ``read_session_factory`` already resolves to the primary engine when no
        replica is configured, so this mirrors ``get_read_db`` exactly.
        """
        from app.core.database import read_session_factory

        async with read_session_factory() as session:
            yield session

    @provide(scope=Scope.APP)
    def audit_service(
        self, audit: Annotated[AuditService, FromComponent(DEFAULT_COMPONENT)]
    ) -> AuditService:
        return audit

    @provide(scope=Scope.APP)
    def cache(
        self, cache: Annotated[BaseCache, FromComponent(DEFAULT_COMPONENT)]
    ) -> BaseCache:
        return cache
