from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    File,
    Header,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import exists, func, literal, select

from app.api.deps import (
    get_current_user,
    get_current_user_optional,
    get_news_service,
    get_read_news_service,
)
from app.api.deps.etag import _set_language_headers, cached_endpoint
from app.api.utils import save_upload
from app.api.validation import (
    raise_forbidden,
    raise_not_found,
    raise_validation_error,
    require_admin,
)
from app.core.cache_versioning import news_cache_version
from app.core.config import settings
from app.core.container import get_notification_service, get_vector_service
from app.core.database import get_read_db
from app.core.localization import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    resolve_locale,
)
from app.core.protocols import AsyncDatabaseSession
from app.core.ratelimit import sensitive_route_limit
from app.deps.cache import etag_matches, format_etag, get_cache
from app.models import models
from app.schemas import schemas
from app.services.file_scanner import scan_for_malware
from app.services.news_service import NewsService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/news", tags=["news"])

_NEWS_CACHE_CONTROL = "public, max-age=60, stale-while-revalidate=120"
_NEWS_LIST_CACHE_PREFIX = news_cache_version.prefix
_LEGACY_NEWS_LIST_CACHE_KEY = "news:list"
_LEGACY_NEWS_ITEM_PREFIX = "news:item"
_CACHE_LOCALES = frozenset(SUPPORTED_LOCALES)


def _normalized_cache_locale(locale: str | None) -> str:
    """Normalize locale string for cache key purposes."""
    if locale is None:
        return DEFAULT_LOCALE
    if locale in SUPPORTED_LOCALES:
        return locale
    return DEFAULT_LOCALE


async def _get_news_list_version(cache: Any | None = None) -> str:
    return await news_cache_version.get_version(cache)


async def _increment_news_list_version(cache: Any | None = None) -> None:
    if cache is not None:
        await news_cache_version.increment(cache)


def _news_item_cache_key(id: uuid.UUID | int, locale: str) -> str:
    return f"ue:news:item:{id}:{locale}"


def _legacy_news_item_cache_key(id: uuid.UUID | int) -> str:
    return f"news:item:{id}"


# Obsolete cache key helpers removed


@router.post(
    "",
    response_model=schemas.NewsOut,
    dependencies=[Depends(sensitive_route_limit(limit_value=settings.rate_limit_news))],
)
async def create_news(
    data: schemas.NewsCreate,
    request: Request,
    background: BackgroundTasks,
    service: NewsService = Depends(get_news_service),
    user: models.User = Depends(get_current_user),
    notifications: NotificationService = Depends(get_notification_service),
) -> schemas.NewsOut:
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)
    record = await service.create_news(data)
    if request:
        await _increment_news_list_version(getattr(request.app.state, "cache", None))
    serialized = service.serialize_news(record, locale)
    await notifications.dispatch_news_created(record.id, locale, background)
    return serialized


@router.get(
    "",
    response_model=schemas.PaginatedNews,
    summary="List News",
    description="Get a paginated list of news articles.",
)
@cached_endpoint(
    version_resolver=news_cache_version,
    cache_prefix=_NEWS_LIST_CACHE_PREFIX,
    cache_control=_NEWS_CACHE_CONTROL,
)
async def news_list(
    request: Request,
    response: Response,
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
    cursor: str | None = Query(None, description="Pagination cursor"),
    if_none_match: str | None = Header(default=None),
    service: NewsService = Depends(get_read_news_service),
    user: models.User | None = Depends(get_current_user_optional),
) -> schemas.PaginatedNews | Response | Any:
    """
    Get paginated list of news articles.

    - **limit**: Items to return (1-100, default 20)
    - **cursor**: Pagination cursor for next page

    Returns news ordered by creation date (newest first).
    """
    locale = resolve_locale(request=request)
    normalized_locale = _normalized_cache_locale(locale)

    results = await service.list_news(
        limit=limit,
        cursor=cursor,
        current_user_id=user.id if user else None,
        search=None,
        locale=normalized_locale,
    )

    return results


@router.get(
    "/{id}",
    response_model=schemas.NewsOut,
    summary="Get News Item",
    description="Get a specific news article by ID.",
)
@cached_endpoint(
    version_resolver=news_cache_version,
    cache_prefix="ue:news:item",
    cache_control=_NEWS_CACHE_CONTROL,
)
async def get_news(
    id: uuid.UUID,
    request: Request,
    response: Response,
    if_none_match: str | None = Header(default=None),
    user: models.User | None = Depends(get_current_user_optional),
    db: AsyncDatabaseSession = Depends(get_read_db),
    service: NewsService = Depends(get_read_news_service),
) -> schemas.NewsOut | Response | Any:
    """
    Get a specific news article by ID.

    - **id**: News item ID

    Returns 404 if not found.
    """
    locale = resolve_locale(request=request)

    # Subqueries for counts
    likes_sub = (
        select(func.count(models.NewsLike.id))
        .where(models.NewsLike.news_id == id)
        .scalar_subquery()
        .label("likes_count")
    )
    comments_sub = (
        select(func.count(models.NewsComment.id))
        .where(models.NewsComment.news_id == id)
        .scalar_subquery()
        .label("comments_count")
    )

    # Subquery for user like status
    current_user_id = user.id if user else None
    is_liked_sub = literal(False).label("is_liked")
    if current_user_id:
        is_liked_sub = (
            select(
                exists().where(
                    models.NewsLike.news_id == models.News.id,
                    models.NewsLike.user_id == current_user_id,
                )
            )
            .scalar_subquery()
            .label("is_liked")
        )

    stmt = select(
        models.News,
        likes_sub,
        comments_sub,
        is_liked_sub,
    ).where(models.News.id == id)

    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise_not_found("news", locale)

    news_obj, l_count, c_count, liked = row
    # Map database row to model object with extra attributes
    news_obj.likes_count = l_count or 0
    news_obj.comments_count = c_count or 0
    news_obj.is_liked = bool(liked)

    serialized = service.serialize_news(news_obj, locale)
    return serialized


@router.patch(
    "/{id}",
    response_model=schemas.NewsOut,
    dependencies=[Depends(sensitive_route_limit(limit_value=settings.rate_limit_news))],
)
async def update_news(
    id: uuid.UUID,
    request: Request,
    data: schemas.NewsUpdate | None = Body(default=None),
    service: NewsService = Depends(get_news_service),
    user: models.User = Depends(get_current_user),
) -> schemas.NewsOut:
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)

    try:
        updated = await service.update_news(id, data or schemas.NewsUpdate())  # type: ignore[arg-type]
    except ValueError:
        raise_not_found("news", locale)

    if request:
        await _increment_news_list_version(getattr(request.app.state, "cache", None))
    cache = get_cache()
    if cache.enabled:
        await cache.invalidate(
            _news_item_cache_key(id, locale), _legacy_news_item_cache_key(id)
        )
    serialized = service.serialize_news(updated, locale)
    return serialized


@router.delete(
    "/{id}",
    response_model=dict,
    dependencies=[Depends(sensitive_route_limit(limit_value=settings.rate_limit_news))],
)
async def delete_news(
    id: uuid.UUID,
    request: Request,
    service: NewsService = Depends(get_news_service),
    user: models.User = Depends(get_current_user),
) -> dict[str, bool]:
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)

    deleted = await service.delete_news(id)  # type: ignore[arg-type]
    if not deleted:
        raise_not_found("news", locale)

    if request:
        await _increment_news_list_version(getattr(request.app.state, "cache", None))
    cache = get_cache()
    if cache.enabled:
        await cache.invalidate(
            _news_item_cache_key(id, locale), _legacy_news_item_cache_key(id)
        )
    return {"ok": True}


@router.post(
    "/{id}/like",
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_interactions))
    ],
)
async def like_news(
    id: uuid.UUID,
    request: Request,
    service: NewsService = Depends(get_news_service),
    user: models.User = Depends(get_current_user),
) -> dict[str, bool]:
    locale = resolve_locale(request=request, user=user)
    news = await service.get_news_item(id)  # type: ignore[arg-type]
    if not news:
        raise_not_found("news", locale)
    is_liked = await service.toggle_like(id, user.id)  # type: ignore[arg-type]
    return {"is_liked": is_liked}


@router.post(
    "/{id}/comment",
    response_model=schemas.NewsCommentOut,
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_interactions))
    ],
)
async def comment_on_news(
    id: uuid.UUID,
    request: Request,
    background: BackgroundTasks,
    content: str = Body(..., embed=True),
    service: NewsService = Depends(get_news_service),
    user: models.User = Depends(get_current_user),
    notifications: NotificationService = Depends(get_notification_service),
) -> schemas.NewsCommentOut | dict[str, Any]:
    locale = resolve_locale(request=request, user=user)
    news = await service.get_news_item(id)  # type: ignore[arg-type]
    if not news:
        raise_not_found("news", locale)
    if not content.strip():
        raise_validation_error("errors.validation.required", locale)

    comment = await service.create_comment(id, user.id, content)  # type: ignore[arg-type]

    # Notify admins about new comment
    await notifications.dispatch_comment_created(  # type: ignore[attr-defined]
        id, comment.id, user.id, locale, background
    )

    return {
        "id": comment.id,
        "content": comment.content,
        "user_id": comment.user_id,
        "user_name": user.profile.full_name if user.profile else str(user.email),
        "created_at": comment.created_at,
    }


@router.get("/{id}/interactions", response_model=schemas.NewsInteractionsOut)
async def get_news_interact(
    id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: NewsService = Depends(get_read_news_service),
    user: models.User | None = Depends(get_current_user_optional),
) -> schemas.NewsInteractionsOut:
    locale = resolve_locale(request=request)
    news = await service.get_news_item(id)  # type: ignore[arg-type]
    if not news:
        raise_not_found("news", locale, resource_id=id)

    interactions = await service.get_interactions(
        id,  # type: ignore[arg-type]
        user.id if user else None,
        limit=limit,
        offset=offset,
    )
    return schemas.NewsInteractionsOut.model_validate(interactions)


@router.patch("/comments/{comment_id}", response_model=schemas.NewsCommentOut)
async def update_comment(
    comment_id: uuid.UUID,
    request: Request,
    data: schemas.NewsCommentUpdate,
    service: NewsService = Depends(get_news_service),
    user: models.User = Depends(get_current_user),
) -> schemas.NewsCommentOut | dict[str, Any]:
    locale = resolve_locale(request=request, user=user)
    try:
        comment = await service.update_comment(comment_id, user.id, data.content)  # type: ignore[arg-type]
        return {
            "id": comment.id,
            "content": comment.content,
            "user_id": comment.user_id,
            "user_name": user.profile.full_name if user.profile else str(user.email),
            "created_at": comment.created_at,
        }
    except LookupError:
        raise_not_found("news", locale, exact_key="errors.not_found")
    except PermissionError:
        raise_forbidden(locale)


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: uuid.UUID,
    request: Request,
    service: NewsService = Depends(get_news_service),
    user: models.User = Depends(get_current_user),
) -> dict[str, bool]:
    locale = resolve_locale(request=request, user=user)
    try:
        await service.delete_comment(
            comment_id,  # type: ignore[arg-type]
            user.id,
            is_admin=(user.role == "admin"),
        )
        return {"ok": True}
    except LookupError:
        raise_not_found("news", locale, exact_key="errors.not_found")
    except PermissionError:
        raise_forbidden(locale)


@router.post(
    "/upload_image",
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_upload))
    ],
)
async def upload_news_image(
    file: UploadFile = File(...),
    *,
    request: Request,
    user: models.User = Depends(get_current_user),
) -> dict[str, str]:
    locale = resolve_locale(request=request, user=user)
    require_admin(user, locale)
    await scan_for_malware(file, locale=locale, size_bytes=file.size)
    url = await save_upload(file, "news_images", "news", locale=locale)
    return {"url": url}


@router.get(
    "/search/semantic",
    response_model=list[schemas.NewsOut],
    dependencies=[
        Depends(sensitive_route_limit(limit_value=settings.rate_limit_graphql))
    ],
)
async def semantic_search(
    request: Request,
    response: Response,
    query: str = Query(..., min_length=3),
    limit: int = Query(5, ge=1, le=20),
    min_score: float = Query(0.7, ge=0.0, le=1.0),
    if_none_match: str | None = Header(default=None),
    db: AsyncDatabaseSession = Depends(get_read_db),
    vector_service: Any = Depends(get_vector_service),
    service: NewsService = Depends(get_read_news_service),
) -> list[schemas.NewsOut] | Response:
    """
    Semantic search for news articles using embeddings.
    """
    locale = resolve_locale(request=request)
    normalized_locale = _normalized_cache_locale(locale)

    # Note: We don't cache semantic search results easily due to query variety,
    # but we can use ETag based on the content version.
    cache = get_cache()
    version = await _get_news_list_version(cache)
    etag = format_etag(f"semantic:{version}:{query}:{limit}:{min_score}")
    if etag_matches(etag, if_none_match):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    embedding = await vector_service.get_embedding(query)
    results = await vector_service.search_similar(
        models.News, embedding, limit=limit, min_score=min_score
    )

    items = [service.serialize_news(item, locale) for item in results]
    response.headers["ETag"] = etag
    _set_language_headers(response, normalized_locale)
    return items


__all__ = ["router"]
