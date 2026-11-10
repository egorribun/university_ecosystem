"""Observe rebuild progress at the search transport boundary."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine
from typing import Any


async def provision_search_tenant(db: Any, monkeypatch: Any) -> None:
    """Give rebuild fixtures a real active organization for their preflight."""
    from app.core.config import settings
    from app.models import Tenant

    tenant_id = uuid.UUID("c3333333-3333-4333-8333-333333333333")
    db.add(Tenant(id=tenant_id, name="Search tests", slug=f"search-{tenant_id}"))
    await db.flush()
    monkeypatch.setattr(settings, "mvp_tenant_id", tenant_id)


class RebuildProgress:
    """Reject repeated documents while owning every task used to observe them."""

    def __init__(self) -> None:
        self.deliveries: dict[str, list[str]] = {}
        self._duplicate = asyncio.Event()
        self._release_duplicate = asyncio.Event()

    async def record(self, index: str, documents: list[dict[str, Any]]) -> None:
        delivered = self.deliveries.setdefault(index, [])
        for document in documents:
            document_id = document["id"]
            if document_id in delivered:
                self._duplicate.set()
                # Keep the faulty scan at the observed delivery until its owner
                # cancels it, instead of allowing an unbounded pagination loop.
                await self._release_duplicate.wait()
            delivered.append(document_id)

    async def complete[T](self, operation: Coroutine[Any, Any, T]) -> T:
        rebuild = asyncio.create_task(operation)
        duplicate = asyncio.create_task(self._duplicate.wait())
        try:
            await asyncio.wait(
                (rebuild, duplicate), return_when=asyncio.FIRST_COMPLETED
            )
            assert not self._duplicate.is_set(), (
                "search rebuild delivered a document more than once"
            )
            return await rebuild
        finally:
            rebuild.cancel()
            duplicate.cancel()
            await asyncio.gather(rebuild, duplicate, return_exceptions=True)
