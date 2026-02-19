"""Query batching utilities for N+1 query prevention."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import InstrumentedAttribute, RelationshipProperty
    from sqlalchemy.sql import Select

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def batch_load_ids[T](
    session: AsyncSession,
    model: type[T],
    ids: Sequence[int | str],
    id_column: InstrumentedAttribute | None = None,
    batch_size: int = 100,
) -> list[T]:
    """
    Efficiently load multiple records by ID in batches.

    Prevents N+1 by loading all records in a single batched query
    instead of fetching one by one.

    Args:
        session: Database session
        model: SQLAlchemy model class
        ids: Sequence of IDs to load
        id_column: Column to match IDs against (default: model.id)
        batch_size: Maximum IDs per query batch

    Returns:
        List of loaded model instances
    """
    if not ids:
        return []

    column = id_column if id_column is not None else model.id
    unique_ids = list(set(ids))
    results: list[T] = []

    for batch_start in range(0, len(unique_ids), batch_size):
        batch_ids = unique_ids[batch_start : batch_start + batch_size]
        stmt = select(model).where(column.in_(batch_ids))
        batch_result = await session.scalars(stmt)
        results.extend(batch_result.all())

    return results


def eager_load_options(
    *relationships: RelationshipProperty | InstrumentedAttribute,
    strategy: str = "selectin",
) -> list:
    """
    Create eager loading options for relationships.

    Use 'selectin' for collections (avoids cartesian product).
    Use 'joined' for single-valued relationships.

    Args:
        relationships: Relationship attributes to eagerly load
        strategy: Loading strategy - 'selectin' or 'joined'

    Returns:
        List of loader options to pass to select().options()
    """
    loader_fn = selectinload if strategy == "selectin" else joinedload
    return [loader_fn(rel) for rel in relationships]


def apply_eager_loading[T](
    stmt: Select[tuple[T]],
    *relationships: RelationshipProperty | InstrumentedAttribute,
    strategy: str = "selectin",
) -> Select[tuple[T]]:
    """
    Apply eager loading to a select statement.

    Args:
        stmt: SQLAlchemy select statement
        relationships: Relationships to eagerly load
        strategy: 'selectin' (default, good for collections) or 'joined'

    Returns:
        Select statement with eager loading options applied
    """
    options = eager_load_options(*relationships, strategy=strategy)
    return stmt.options(*options)


class QueryBatcher:
    """
    Batch multiple single-item queries into a single batch query.

    Use when you have a pattern like:
        for item_id in item_ids:
            item = await session.get(Model, item_id)

    Replace with:
        batcher = QueryBatcher(session, Model)
        for item_id in item_ids:
            batcher.add(item_id)
        items = await batcher.execute()
    """

    def __init__(
        self,
        session: AsyncSession,
        model: type[T],
        id_column: InstrumentedAttribute | None = None,
    ) -> None:
        self._session = session
        self._model = model
        self._id_column = id_column if id_column is not None else model.id
        self._pending_ids: list[int | str] = []

    def add(self, item_id: int | str) -> None:
        """Add an ID to be loaded in the batch."""
        self._pending_ids.append(item_id)

    async def execute(self) -> dict[int | str, T]:
        """
        Execute the batch query.

        Returns:
            Dictionary mapping IDs to loaded instances.
        """
        if not self._pending_ids:
            return {}

        items = await batch_load_ids(
            self._session,
            self._model,
            self._pending_ids[:],
            id_column=self._id_column,
        )

        result: dict[int | str, T] = {}
        for item in items:
            item_id = getattr(item, self._id_column.key)
            result[item_id] = item

        self._pending_ids.clear()
        return result


async def prefetch_related(
    session: AsyncSession,
    items: Sequence[T],
    relationship: InstrumentedAttribute,
    foreign_key_getter: Callable[[T], int | str | None],
) -> dict[int | str, object]:
    """
    Prefetch related objects for a collection of items.

    Useful when you have items loaded without a relationship
    and need to load the related objects in batch.

    Args:
        session: Database session
        items: Collection of parent objects
        relationship: The relationship to prefetch
        foreign_key_getter: Function to extract FK from parent item

    Returns:
        Dictionary mapping FK values to related objects
    """
    related_model = relationship.property.mapper.class_

    foreign_keys = [
        fk for item in items if (fk := foreign_key_getter(item)) is not None
    ]

    if not foreign_keys:
        return {}

    related_items = await batch_load_ids(session, related_model, foreign_keys)
    return {item.id: item for item in related_items}
