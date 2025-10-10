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
from app.api.push import NotifyBody
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import RateLimitExceeded, RateLimitInfo, enforce_rate_limit
from app.models.models import PushSubscription, User
from app.services.notifications import prepare_push_payload_for_user
from app.services.push_schema import ensure_push_subscription_schema
from app.services.push_topics import (
    normalize_topic,
    normalize_topics,
    resolve_topics,
    subscription_supports_topic,
)
from app.services.webpush import WebPushResult, send_web_push

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/push", tags=["push"])
legacy_router = APIRouter(prefix="/webpush", tags=["webpush"])


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
    updated_at: datetime | None = None
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


def _serialize_subscription(subscription: PushSubscription) -> PushSubscriptionOut:
    topics = normalize_topics(subscription.topics or [])
    created_at = subscription.created_at
    if created_at is None:
        created_at = subscription.last_seen_at or datetime.now(UTC)
    data = {
        "id": subscription.id,
        "user_id": subscription.user_id,
        "endpoint": subscription.endpoint,
        "p256dh": subscription.p256dh,
        "auth": subscription.auth,
        "created_at": created_at,
        "user_agent": subscription.user_agent,
        "last_seen_at": subscription.last_seen_at,
        "updated_at": subscription.last_seen_at,
        "topics": topics,
    }
    return PushSubscriptionOut.model_validate(data)


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


class PushTestRequest(NotifyBody):
    user_id: int | None = Field(
        default=None, description="Target user id for testing", ge=1
    )
    title: str = Field(
        default="Тестовое веб-push уведомление",
        description="Notification title",
    )
    body: str | None = Field(
        default="Проверка доставки уведомлений",
        description="Notification body",
    )
    url: str | None = Field(
        default=None, description="URL to open when clicking the notification"
    )


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
    await ensure_push_subscription_schema(db)
    endpoint, p256dh, auth = await _validate_subscription_payload(payload)

    client_host = request.client.host if request.client else None
    try:
        await enforce_rate_limit(
            identifier=f"user:{user.id}",
            namespace="push:subscribe:user",
            limit=20,
            window_seconds=60,
            redis_url=settings.rate_limit_storage_uri,
        )
        if client_host:
            await enforce_rate_limit(
                identifier=f"ip:{client_host}",
                namespace="push:subscribe:ip",
                limit=60,
                window_seconds=60,
                redis_url=settings.rate_limit_storage_uri,
            )
    except RateLimitExceeded as exc:
        info: RateLimitInfo = exc.info
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Слишком много запросов подписки. Попробуйте позже.",
                "retry_after": info.retry_after,
            },
        ) from None

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
            existing.user_id = user.id
            existing.user_agent = user_agent or None
            existing.last_seen_at = now
            if existing.created_at is None:
                existing.created_at = now
            existing.topics = _resolve_topics()
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
            if subscription.created_at is None:
                subscription.created_at = now
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

    return _serialize_subscription(subscription)


@router.patch("/subscribe/topics", response_model=PushSubscriptionOut)
async def update_subscription_topics(
    payload: PushSubscriptionTopicsUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> PushSubscriptionOut:
    await ensure_push_subscription_schema(db)
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
    return _serialize_subscription(subscription)


@router.post("/unsubscribe")
async def unsubscribe(
    payload: PushSubscriptionDelete,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, bool]:
    await ensure_push_subscription_schema(db)
    endpoint = payload.endpoint.strip()
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_subscription",
                "message": "Endpoint is required",
            },
        )

    client_host = request.client.host if request.client else None
    try:
        await enforce_rate_limit(
            identifier=f"user:{user.id}",
            namespace="push:unsubscribe:user",
            limit=20,
            window_seconds=60,
            redis_url=settings.rate_limit_storage_uri,
        )
        if client_host:
            await enforce_rate_limit(
                identifier=f"ip:{client_host}",
                namespace="push:unsubscribe:ip",
                limit=60,
                window_seconds=60,
                redis_url=settings.rate_limit_storage_uri,
            )
    except RateLimitExceeded as exc:
        info: RateLimitInfo = exc.info
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Слишком много попыток отключить уведомления.",
                "retry_after": info.retry_after,
            },
        ) from None

    existing = (
        await db.execute(
            select(PushSubscription).where(
                PushSubscription.endpoint == endpoint,
                PushSubscription.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not existing:
        return {"ok": True, "removed": False}

    await db.delete(existing)
    await db.commit()
    return {"ok": True, "removed": True}


@router.post("/test", response_model=SendTestResponse)
async def send_test(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    payload: PushTestRequest | None = None,
) -> SendTestResponse:
    await ensure_push_subscription_schema(db)
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "Admin access required"},
        )

    if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Web push is not configured",
        )

    client_host = request.client.host if request and request.client else None
    try:
        await enforce_rate_limit(
            identifier=f"user:{user.id}",
            namespace="push:test:user",
            limit=5,
            window_seconds=60,
            redis_url=settings.rate_limit_storage_uri,
        )
        if client_host:
            await enforce_rate_limit(
                identifier=f"ip:{client_host}",
                namespace="push:test:ip",
                limit=15,
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

    target_id = payload.user_id if payload and payload.user_id else user.id
    target = await db.get(User, target_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "user_not_found", "message": "Target user not found"},
        )

    subscriptions = (
        (
            await db.execute(
                select(PushSubscription)
                .options(selectinload(PushSubscription.user))
                .where(PushSubscription.user_id == target.id)
            )
        )
        .scalars()
        .all()
    )
    if not subscriptions:
        return SendTestResponse(
            sent=0, removed=0, failed=0, detail="No subscriptions found"
        )

    normalized_topic = normalize_topic(payload.topic if payload else None) or "system"
    base_url = payload.url if payload and payload.url else settings.app_base_url or "/"
    body = payload.body if payload else None
    title = payload.title if payload else "Тестовое веб-push уведомление"
    message = {
        "title": title,
        "body": body or "Проверка доставки уведомлений",
        "url": base_url,
    }
    if normalized_topic:
        message["topic"] = normalized_topic

    optional_fields = ("tag", "badge", "ttl", "urgency", "actions", "data")
    if payload:
        for field in optional_fields:
            value = getattr(payload, field, None)
            if value is not None:
                message[field] = value

    sent = 0
    removed = 0
    failed = 0
    now_time = datetime.now().astimezone().time()
    for sub in subscriptions:
        if not subscription_supports_topic(sub, normalized_topic):
            continue
        prepared = prepare_push_payload_for_user(
            message, getattr(sub, "user", None), now_time=now_time
        )
        result: WebPushResult = await run_in_threadpool(send_web_push, sub, prepared)
        if result.status == "sent":
            sent += 1
        elif result.status == "gone":
            removed += 1
        else:
            failed += 1
    logger.info(
        "push.test.summary",
        extra={
            "user_id": user.id,
            "target_user_id": target.id,
            "sent": sent,
            "removed": removed,
            "failed": failed,
        },
    )
    detail = None
    if failed and not sent:
        detail = "Не удалось отправить тестовое уведомление"
    return SendTestResponse(sent=sent, removed=removed, failed=failed, detail=detail)


legacy_router.add_api_route(
    "/vapid-public-key",
    get_vapid_public_key,
    methods=["GET"],
)
legacy_router.add_api_route(
    "/subscribe",
    subscribe,
    methods=["POST"],
    response_model=PushSubscriptionOut,
)
legacy_router.add_api_route(
    "/subscribe/topics",
    update_subscription_topics,
    methods=["PATCH"],
    response_model=PushSubscriptionOut,
)
legacy_router.add_api_route(
    "/unsubscribe",
    unsubscribe,
    methods=["POST"],
)
legacy_router.add_api_route(
    "/send-test",
    send_test,
    methods=["POST"],
    response_model=SendTestResponse,
)
