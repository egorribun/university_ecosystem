"""Keeps the Elasticsearch ``news`` and ``events`` indices in step with the DB.

``GET /api/v1/search`` only reads from these indices, so without an indexer it
always answers with empty groups.  Documents are written from the domain-event
handlers (created / updated) and removed from the delete paths; ``reindex_all``
rebuilds both indices from scratch (the ``search reindex`` CLI command) and is
the recovery path after an Elasticsearch outage or a mapping change.

Search is a non-critical read model: Elasticsearch being unavailable must never
fail the write that triggered the event, so transport errors are logged and the
operation is skipped (``reindex_all`` repairs the drift).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import elasticsearch
from sqlalchemy import select

import app.models as models
from app.core.config import settings
from app.core.database import async_session
from app.core.logging import get_logger
from app.services.search import (
    EVENTS_MAPPINGS,
    NEWS_MAPPINGS,
    SearchService,
)

logger = get_logger(__name__)

NEWS_INDEX = "news"
EVENTS_INDEX = "events"

# Everything that can go wrong talking to Elasticsearch without it being a bug.
_SEARCH_UNAVAILABLE = (
    OSError,
    ConnectionError,
    TimeoutError,
    elasticsearch.TransportError,
    elasticsearch.ApiError,
)


def build_search_service() -> SearchService:
    """Construct a client from the application settings."""
    user = settings.elasticsearch_user
    password = settings.elasticsearch_password
    return SearchService(
        hosts=settings.elasticsearch_url,
        http_auth=(user, password) if password else None,
    )


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def news_document(news: models.News) -> dict[str, Any]:
    return {
        "id": str(news.id),
        "title": news.title,
        "title_en": news.title_en,
        "content": news.content,
        "content_en": news.content_en,
        "created_at": _iso(news.created_at),
    }


def event_document(event: models.Event) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "title": event.title,
        "title_en": event.title_en,
        "description": event.description,
        "description_en": event.description_en,
        "location": event.location,
        "category": event.event_type,
        "start_time": _iso(event.starts_at),
        "end_time": _iso(event.ends_at),
    }


async def _guarded[T](
    operation: Callable[[SearchService], Awaitable[T]],
) -> T | None:
    service = build_search_service()
    try:
        return await operation(service)
    except _SEARCH_UNAVAILABLE as exc:
        logger.warning("search_index_unavailable: %s", exc)
        return None
    finally:
        await service.close()


async def index_news(news_id: uuid.UUID | str | None) -> None:
    if news_id is None:
        return
    async with async_session() as db:
        news = await db.get(
            models.News, uuid.UUID(news_id) if isinstance(news_id, str) else news_id
        )
    if news is None:
        return
    document = news_document(news)
    await _guarded(
        lambda service: service.index_document(NEWS_INDEX, document["id"], document)
    )


async def index_event(event_id: uuid.UUID | str | None) -> None:
    """Index an active event; deactivated or missing events leave the index."""
    if event_id is None:
        return
    async with async_session() as db:
        event = await db.get(
            models.Event, uuid.UUID(event_id) if isinstance(event_id, str) else event_id
        )
    if event is None or not event.is_active:
        await remove_document(EVENTS_INDEX, event_id)
        return
    document = event_document(event)
    await _guarded(
        lambda service: service.index_document(EVENTS_INDEX, document["id"], document)
    )


async def remove_document(index: str, document_id: uuid.UUID | int | str) -> None:
    await _guarded(lambda service: service.delete_document(index, str(document_id)))


async def reindex_all(*, batch_size: int = 200) -> dict[str, int]:
    """Build replacements and atomically publish them only after complete success.

    Run during a maintenance window with content writes and outbox delivery paused:
    this recovery operation does not replay changes made while the scan is running.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    counts = {NEWS_INDEX: 0, EVENTS_INDEX: 0}
    service = build_search_service()
    replacements = {name: f"{name}-rebuild-{uuid.uuid4().hex}" for name in counts}
    publication_started = False
    try:
        await service.ensure_index(replacements[NEWS_INDEX], NEWS_MAPPINGS)
        await service.ensure_index(replacements[EVENTS_INDEX], EVENTS_MAPPINGS)
        async with async_session() as db:
            for index, model, builder, condition in (
                (NEWS_INDEX, models.News, news_document, None),
                (EVENTS_INDEX, models.Event, event_document, models.Event.is_active),
            ):
                statement = select(model).order_by(model.id)
                if condition is not None:
                    statement = statement.where(condition.is_(True))
                last_id = None
                while True:
                    page = statement.limit(batch_size)
                    if last_id is not None:
                        page = page.where(model.id > last_id)
                    rows = (await db.execute(page)).scalars().all()
                    if not rows:
                        break
                    ok, failed = await service.bulk_index(
                        replacements[index], [builder(row) for row in rows]
                    )
                    if failed or ok != len(rows):
                        raise RuntimeError(
                            f"Search rebuild bulk failed for {index}: {ok} indexed, {failed} failed"
                        )
                    counts[index] += ok
                    last_id = rows[-1].id
        publication_started = True
        await service.publish_rebuilt_indices(replacements)
    finally:
        # A transport timeout during the alias switch has an uncertain outcome.
        # Retain replacements then: deleting them could destroy the live indices.
        if not publication_started:
            for replacement in replacements.values():
                try:
                    await service.delete_index(replacement)
                except _SEARCH_UNAVAILABLE:
                    logger.warning(
                        "Unable to clean failed search rebuild %s", replacement
                    )
        await service.close()
    return counts
