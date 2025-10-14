import logging
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.deps import get_current_user
from app.api.utils import save_upload
from app.core.database import get_db
from app.deps.cache import etag_matches, format_etag, get_cache
from app.localization import resolve_locale, translate
from app.models import models
from app.schemas import schemas
from app.services.notifications import notify_about_news
from app.utils.files import delete_static_file

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/news", tags=["news"])

_NEWS_LIST_CACHE_KEY = "news:list"


def _news_item_cache_key(news_id: int) -> str:
    return f"news:item:{news_id}"


@router.post("", response_model=schemas.NewsOut)
async def create_news(
    data: schemas.NewsCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    record = await crud.create_news(db, data)
    cache = get_cache()
    await cache.invalidate(_NEWS_LIST_CACHE_KEY)
    try:
        await notify_about_news(db, record, locale=locale)
    except Exception:
        logger.exception(
            "Failed to dispatch news notification", extra={"news_id": record.id}
        )
    return record


@router.get("", response_model=List[schemas.NewsOut])
async def news_list(
    response: Response,
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    cache = get_cache()
    if cache.enabled:
        cached = await cache.get(_NEWS_LIST_CACHE_KEY)
        if cached:
            etag_header = format_etag(cached.etag)
            if etag_matches(cached.etag, if_none_match):
                return Response(
                    status_code=status.HTTP_304_NOT_MODIFIED,
                    headers={"ETag": etag_header},
                )
            response.headers["ETag"] = etag_header
            return cached.payload

    rows = await crud.get_news_list(db)
    models_out = [schemas.NewsOut.model_validate(item) for item in rows]
    payload = jsonable_encoder(models_out)

    if cache.enabled:
        entry = await cache.set(_NEWS_LIST_CACHE_KEY, payload)
        response.headers["ETag"] = format_etag(entry.etag)
    return payload


@router.get("/{id}", response_model=schemas.NewsOut)
async def get_news(
    id: int,
    request: Request,
    response: Response,
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    locale = resolve_locale(request=request)
    cache = get_cache()
    cache_key = _news_item_cache_key(id)
    if cache.enabled:
        cached = await cache.get(cache_key)
        if cached:
            etag_header = format_etag(cached.etag)
            if etag_matches(cached.etag, if_none_match):
                return Response(
                    status_code=status.HTTP_304_NOT_MODIFIED,
                    headers={"ETag": etag_header},
                )
            response.headers["ETag"] = etag_header
            return cached.payload
    q = await db.get(models.News, id)
    if not q:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.news.not_found", locale=locale),
        )
    model_out = schemas.NewsOut.model_validate(q)
    payload = jsonable_encoder(model_out)
    if cache.enabled:
        entry = await cache.set(cache_key, payload)
        response.headers["ETag"] = format_etag(entry.etag)
    return payload


@router.patch("/{id}", response_model=schemas.NewsOut)
async def update_news(
    id: int,
    data: schemas.NewsCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    news = await db.get(models.News, id)
    if not news:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.news.not_found", locale=locale),
        )
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    old_image_url = news.image_url
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(news, field, value)
    await db.commit()
    await db.refresh(news)
    if old_image_url and news.image_url != old_image_url:
        await delete_static_file(old_image_url)
    cache = get_cache()
    await cache.invalidate(_NEWS_LIST_CACHE_KEY, _news_item_cache_key(id))
    return news


@router.delete("/{id}", response_model=dict)
async def delete_news(
    id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    news = await db.get(models.News, id)
    if not news:
        raise HTTPException(
            status_code=404,
            detail=translate("errors.news.not_found", locale=locale),
        )
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    image_url = news.image_url
    await db.delete(news)
    await db.commit()
    if image_url:
        await delete_static_file(image_url)
    cache = get_cache()
    await cache.invalidate(_NEWS_LIST_CACHE_KEY, _news_item_cache_key(id))
    return {"ok": True}


@router.post("/upload_image")
async def upload_news_image(
    file: UploadFile = File(...),
    *,
    request: Request,
    user: models.User = Depends(get_current_user),
):
    locale = resolve_locale(request=request, user=user)
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail=translate("errors.forbidden", locale=locale),
        )
    url = await save_upload(file, "news_images", "news")
    return {"url": url}


__all__ = ["router"]
