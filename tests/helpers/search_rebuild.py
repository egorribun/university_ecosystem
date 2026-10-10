"""Observe rebuild progress at the search transport boundary."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any


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
