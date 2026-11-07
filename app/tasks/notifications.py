import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.config import settings
from app.core.database import async_session
from app.core.nats_broker import broker
from app.core.tenant import bypass_rls_ctx, canonical_tenant_id, tenant_id_ctx
from app.models import Event, News, NewsComment, User
from app.services.notifications.news_events import (
    notify_about_comment as _notify_about_comment,
)
from app.services.notifications.news_events import (
    notify_about_event as _notify_about_event,
)
from app.services.notifications.news_events import (
    notify_about_news as _notify_about_news,
)


def _normalize_task_uuid(value: uuid.UUID | int | str) -> uuid.UUID:
    """Restore UUID-valued IDs after JSON transport while keeping legacy ints."""
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, int):
        return uuid.UUID(int=value)
    return uuid.UUID(value)


def _resolve_notification_tenant(tenant_id: uuid.UUID | str | None) -> str:
    """Resolve a task tenant claim; explicit claims are not verified here."""
    configured_tenant_id = settings.mvp_tenant_id
    if tenant_id is None:
        if configured_tenant_id is None:
            raise RuntimeError("Notification task requires a tenant identity")
        tenant_value = str(configured_tenant_id)
    elif isinstance(tenant_id, uuid.UUID | str):
        tenant_value = str(tenant_id)
    else:
        raise ValueError("Invalid notification task tenant identity")

    try:
        resolved_tenant_id = canonical_tenant_id(tenant_value)
    except ValueError:
        raise ValueError("Invalid notification task tenant identity") from None

    if configured_tenant_id is not None and resolved_tenant_id != str(
        configured_tenant_id
    ):
        raise ValueError("Notification task tenant differs from configured MVP tenant")

    return resolved_tenant_id


@contextmanager
def _notification_task_tenant_scope(
    tenant_id: uuid.UUID | str | None,
) -> Iterator[None]:
    """Set task scope; an explicit tenant claim requires a trusted publisher."""
    resolved_tenant_id = _resolve_notification_tenant(tenant_id)
    tenant_token = tenant_id_ctx.set(resolved_tenant_id)
    bypass_token = bypass_rls_ctx.set(False)
    try:
        yield
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)


@broker.task()
async def enqueue_news_notification_task(
    news_id: uuid.UUID | int | str,
    locale: str | None = None,
    tenant_id: uuid.UUID | str | None = None,
) -> None:
    """Distributed task for sending news notifications."""
    news_id = _normalize_task_uuid(news_id)
    with _notification_task_tenant_scope(tenant_id):
        async with async_session() as db:
            news = await db.get(News, news_id)
            if news:
                await _notify_about_news(db, news, locale=locale)
                await db.commit()


@broker.task()
async def enqueue_event_notification_task(
    event_id: uuid.UUID | int | str,
    locale: str | None = None,
    tenant_id: uuid.UUID | str | None = None,
) -> None:
    """Distributed task for sending event notifications."""
    event_id = _normalize_task_uuid(event_id)
    with _notification_task_tenant_scope(tenant_id):
        async with async_session() as db:
            event = await db.get(Event, event_id)
            if event:
                await _notify_about_event(db, event, locale=locale)
                await db.commit()


@broker.task()
async def enqueue_comment_notification_task(
    news_id: uuid.UUID | int | str,
    comment_id: uuid.UUID | int | str,
    user_id: uuid.UUID | int | str,
    locale: str | None = None,
    tenant_id: uuid.UUID | str | None = None,
) -> None:
    """Distributed task for sending comment notifications to admins."""
    news_id = _normalize_task_uuid(news_id)
    comment_id = _normalize_task_uuid(comment_id)
    user_id = _normalize_task_uuid(user_id)
    with _notification_task_tenant_scope(tenant_id):
        async with async_session() as db:
            news = await db.get(News, news_id)
            comment = await db.get(NewsComment, comment_id)
            author = await db.get(User, user_id)

            if news and comment and author:
                await _notify_about_comment(db, news, comment, author, locale=locale)
                await db.commit()
