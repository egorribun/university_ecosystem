"""Web push notification routes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import RateLimitExceeded, RateLimitInfo, enforce_rate_limit
from app.models.models import PushSubscription, User
from app.services.notifications import prepare_push_payload_for_user
from app.services.push_topics import (
    normalize_topic,
    normalize_topics,
    resolve_topics,
    subscription_supports_topic,
)
from app.services.webpush import WebPushResult, send_web_push

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webpush", tags=["webpush"])


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(..., description="Base64-encoded public key")
    auth: str = Field(..., description="Authentication secret")

    @field_validator("p256dh", "auth", mode="before")
    @classmethod
    def _ensure_not_blank(cls, value: str) -> str:
        if value is None:
            return ""
        return str(value).strip()


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(..., description="Push subscription endpoint URL")
    keys: PushSubscriptionKeys
    topics: list[str] | None = Field(
        default=None, description="Optional list of topics"
    )
    user_agent: str | None = Field(default=None, description="User agent override")

    @field_validator("endpoint", mode="before")
    @classmethod
    def _normalize_endpoint(cls, value: str) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("topics", mode="before")
    @classmethod
    def _normalize_topics(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return normalize_topics(value)


class PushSubscriptionOut(BaseModel):
    id: int
    user_id: int
    endpoint: str
    p256dh: str
    auth: str
    created_at: datetime
    user_agent: str | None = None
    last_seen_at: datetime | None = None
    topics: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @field_validator("topics", mode="before")
    @classmethod
    def _topics_before(cls, value):
        if not value:
            return []
        if isinstance(value, list):
            return normalize_topics(value)
        return value


class PushSubscriptionTopicsUpdate(BaseModel):
    endpoint: str
    topics: list[str] = Field(default_factory=list)

    @field_validator("endpoint", mode="before")
    @classmethod
    def _normalize_endpoint(cls, value: str) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("topics", mode="before")
    @classmethod
    def _normalize_topics(cls, value):
        if value is None:
            return []
        return normalize_topics(value)


class PushSubscriptionDelete(BaseModel):
    endpoint: str

    @field_validator("endpoint", mode="before")
    @classmethod
    def _normalize_endpoint(cls, value: str) -> str:
        if value is None:
            return ""
        return str(value).strip()


class SendTestResponse(BaseModel):
    sent: int
    removed: int
    failed: int
    detail: str | None = None


async def _validate_subscription_payload(
    data: PushSubscriptionIn,
) -> tuple[str, str, str]:
    endpoint = data.endpoint.strip()
    p256dh = data.keys.p256dh.strip()
    auth = data.keys.auth.strip()
    errors = []
    if not endpoint:
        errors.append({"field": "endpoint", "message": "Endpoint is required"})
    if not p256dh:
        errors.append(
            {"field": "keys.p256dh", "message": "keys.p256dh must not be empty"}
        )
    if not auth:
        errors.append({"field": "keys.auth", "message": "keys.auth must not be empty"})
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_subscription",
                "message": "Subscription payload validation failed",
                "fields": errors,
            },
        )
    return endpoint, p256dh, auth


@router.get("/vapid-public-key")
async def get_vapid_public_key() -> dict[str, str]:
    """Return configured VAPID public key."""
    return {"publicKey": settings.VAPID_PUBLIC_KEY}


@router.post("/subscribe", response_model=PushSubscriptionOut)
async def subscribe(
    payload: PushSubscriptionIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> PushSubscriptionOut:
    endpoint, p256dh, auth = await _validate_subscription_payload(payload)
    user_agent = payload.user_agent or request.headers.get("user-agent") or ""
    user_agent = user_agent.strip()
    if len(user_agent) > 512:
        user_agent = user_agent[:512]

    existing = (
        await db.execute(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
    ).scalar_one_or_none()

    def _resolve_topics() -> list[str]:
        existing_topics = existing.topics if existing else None
        return resolve_topics(payload.topics, existing_topics)

    now = datetime.now(UTC)
    try:
        if existing:
            if existing.user_id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "duplicate_endpoint",
                        "message": "Subscription endpoint already registered",
                    },
                )
            existing.p256dh = p256dh
            existing.auth = auth
            existing.user_agent = user_agent or None
            existing.last_seen_at = now
            existing.topics = _resolve_topics()
            existing.user_id = user.id
            await db.commit()
            await db.refresh(existing)
            subscription = existing
        else:
            subscription = PushSubscription(
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                user_id=user.id,
                user_agent=user_agent or None,
                last_seen_at=now,
                topics=_resolve_topics(),
            )
            db.add(subscription)
            await db.commit()
            await db.refresh(subscription)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "duplicate_endpoint",
                "message": "Subscription endpoint already exists",
            },
        )

    return PushSubscriptionOut.model_validate(subscription)


@router.patch("/subscribe/topics", response_model=PushSubscriptionOut)
async def update_subscription_topics(
    payload: PushSubscriptionTopicsUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> PushSubscriptionOut:
    endpoint = payload.endpoint.strip()
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_subscription",
                "message": "Endpoint is required",
            },
        )

    subscription = (
        await db.execute(
            select(PushSubscription).where(
                PushSubscription.endpoint == endpoint,
                PushSubscription.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "subscription_not_found",
                "message": "Subscription not found",
            },
        )

    subscription.topics = normalize_topics(payload.topics)
    subscription.last_seen_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(subscription)
    return PushSubscriptionOut.model_validate(subscription)


@router.delete("/subscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(
    payload: PushSubscriptionDelete,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    endpoint = payload.endpoint.strip()
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_subscription",
                "message": "Endpoint is required",
            },
        )
    existing = (
        await db.execute(
            select(PushSubscription).where(
                PushSubscription.endpoint == endpoint,
                PushSubscription.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not existing:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    await db.delete(existing)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/send-test", response_model=SendTestResponse)
async def send_test(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> SendTestResponse:
    if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Web push is not configured",
        )

    rate_identifier = f"user:{user.id}"
    try:
        await enforce_rate_limit(
            identifier=rate_identifier,
            namespace="webpush:test",
            limit=3,
            window_seconds=60,
            redis_url=settings.rate_limit_storage_uri,
        )
    except RateLimitExceeded as exc:
        info: RateLimitInfo = exc.info
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many test notifications",
                "retry_after": info.retry_after,
            },
        )

    subscriptions = (
        (
            await db.execute(
                select(PushSubscription)
                .options(selectinload(PushSubscription.user))
                .where(PushSubscription.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    if not subscriptions:
        return SendTestResponse(
            sent=0, removed=0, failed=0, detail="No subscriptions found"
        )

    topic = normalize_topic("system")
    payload = {
        "title": "Тестовое веб-push уведомление",
        "body": "Проверка доставки уведомлений",
        "url": settings.app_base_url or "/",
    }
    if topic:
        payload["topic"] = topic

    sent = 0
    removed = 0
    failed = 0
    now_time = datetime.now().astimezone().time()
    for sub in subscriptions:
        if not subscription_supports_topic(sub, topic):
            continue
        prepared = prepare_push_payload_for_user(
            payload, getattr(sub, "user", None), now_time=now_time
        )
        result: WebPushResult = await run_in_threadpool(send_web_push, sub, prepared)
        if result.status == "sent":
            sent += 1
        elif result.status == "gone":
            removed += 1
        else:
            failed += 1
    logger.info(
        "webpush.send_test.summary",
        extra={"user_id": user.id, "sent": sent, "removed": removed, "failed": failed},
    )
    detail = None
    if failed and not sent:
        detail = "Не удалось отправить тестовое уведомление"
    return SendTestResponse(sent=sent, removed=removed, failed=failed, detail=detail)
