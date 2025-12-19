"""Web push notification routes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import RateLimitExceeded, RateLimitInfo, enforce_rate_limit
from app.localization import resolve_locale, translate
from app.models.models import PushSubscription, User, UserPushTopic
from app.services.notifications import prepare_push_payload_for_user
from app.services.push_schema import ensure_push_subscription_schema
from app.services.push_topics import (
    get_allowed_topics,
    normalize_topic,
    normalize_topics,
    resolve_topics,
    sort_topics,
    subscription_supports_topic,
    synchronize_user_topics,
)
from app.services.webpush import WebPushResult, send_web_push

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/push", tags=["push"])
legacy_router = APIRouter(prefix="/webpush", tags=["webpush"])


class NotificationAction(BaseModel):
    action: str = Field(..., description="Notification action identifier")
    title: str = Field(..., description="Action button title")
    url: str | None = Field(default=None, description="Optional URL to open")
    icon: str | None = Field(default=None, description="Optional icon URL")

    @field_validator("action", "title", mode="before")
    @classmethod
    def _strip(cls, value: str) -> str:
        if value is None:
            return ""
        return str(value).strip()


class NotifyBody(BaseModel):
    title: str
    body: str | None = None
    url: str | None = None
    tag: str | None = None
    badge: str | None = None
    type: str | None = None
    ttl: int | None = None
    urgency: str | None = "normal"
    topic: str | None = None
    actions: list[NotificationAction] | None = None
    data: dict[str, Any] | None = None

    @field_validator("topic", mode="before")
    @classmethod
    def _normalize_topic(cls, value):
        return normalize_topic(value)


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
    topics: list[str] | None = Field(default=None, description="Optional list of topics")
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


class DisableUserPushRequest(BaseModel):
    user_id: int = Field(
        ...,
        ge=1,
        description=translate("notifications.push.disable_user.description"),
    )


class PushTopicsResponse(BaseModel):
    allowed: list[str]
    topics: list[str]
    has_preferences: bool = False
    updated_at: datetime | None = None


class AdminUserTopicsUpdate(BaseModel):
    topics: list[str] = Field(default_factory=list)

    @field_validator("topics", mode="before")
    @classmethod
    def _normalize_topics(cls, value):
        if value is None:
            return []
        return normalize_topics(value, strict=True)


class AdminUserTopicsResponse(BaseModel):
    user_id: int
    email: str
    topics: list[str]
    allowed_topics: list[str]
    updated_at: datetime | None = None


class SendTestResponse(BaseModel):
    total: int = 0
    sent: int
    removed: int
    failed: int
    detail: str | None = None


class PushTestRequest(NotifyBody):
    user_id: int | None = Field(default=None, description="Target user id for testing", ge=1)
    title: str = Field(
        default=translate("notifications.push.test.title_default"),
        description="Notification title",
    )
    body: str | None = Field(
        default=translate("notifications.push.test.body_default"),
        description="Notification body",
    )
    url: str | None = Field(default=None, description="URL to open when clicking the notification")


async def _deliver_to_subscription(
    subscription: PushSubscription, payload: dict[str, Any]
) -> WebPushResult:
    return await run_in_threadpool(send_web_push, subscription, payload)


def _aggregate_results(results: list[WebPushResult], *, failure_detail: str) -> SendTestResponse:
    sent = sum(1 for r in results if r.status == "sent")
    removed = sum(1 for r in results if r.status == "gone")
    failed = sum(1 for r in results if r.status == "error")
    detail = None
    if results and sent == 0 and failed:
        detail = failure_detail
    return SendTestResponse(
        total=len(results),
        sent=sent,
        removed=removed,
        failed=failed,
        detail=detail,
    )


async def _refresh_user_topic_preferences(db: AsyncSession, *, user_id: int) -> None:
    """Synchronize stored user topic preferences with subscription data."""

    topics_rows = (
        await db.execute(select(PushSubscription.topics).where(PushSubscription.user_id == user_id))
    ).scalars()
    aggregated: list[str] = []
    for row in topics_rows:
        if not row:
            continue
        if isinstance(row, list | tuple | set):
            aggregated.extend(str(item) for item in row if item)
        else:
            aggregated.append(str(row))
    normalized = sort_topics(aggregated, settings_obj=settings)
    record = (
        await db.execute(select(UserPushTopic).where(UserPushTopic.user_id == user_id))
    ).scalar_one_or_none()
    if normalized:
        topics_copy = list(normalized)
        if record is None:
            db.add(UserPushTopic(user_id=user_id, topics=topics_copy))
        else:
            record.topics = topics_copy
    elif record is not None:
        await db.delete(record)


async def _validate_subscription_payload(
    data: PushSubscriptionIn,
    *,
    locale: str | None,
) -> tuple[str, str, str]:
    endpoint = data.endpoint.strip()
    p256dh = data.keys.p256dh.strip()
    auth = data.keys.auth.strip()
    errors = []
    if not endpoint:
        errors.append(
            {
                "field": "endpoint",
                "message": translate(
                    "notifications.push.validation.endpoint_required",
                    locale=locale,
                ),
            }
        )
    if not p256dh:
        errors.append(
            {
                "field": "keys.p256dh",
                "message": translate(
                    "notifications.push.validation.keys_p256dh_required",
                    locale=locale,
                ),
            }
        )
    if not auth:
        errors.append(
            {
                "field": "keys.auth",
                "message": translate(
                    "notifications.push.validation.keys_auth_required",
                    locale=locale,
                ),
            }
        )
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_subscription",
                "message": translate("errors.push.subscription_validation_failed", locale=locale),
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
    locale = resolve_locale(request=request, user=user)
    await ensure_push_subscription_schema(db)
    endpoint, p256dh, auth = await _validate_subscription_payload(payload, locale=locale)

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
                "message": translate("errors.rate_limit.push_subscribe", locale=locale),
                "retry_after": info.retry_after,
            },
        ) from None

    user_agent = payload.user_agent or request.headers.get("user-agent") or ""
    user_agent = user_agent.strip()
    if len(user_agent) > 512:
        user_agent = user_agent[:512]

    existing = (
        await db.execute(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    try:
        normalized_topics = resolve_topics(payload.topics, existing.topics if existing else None)
        topics_copy = list(normalized_topics)
        if existing:
            if existing.user_id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "duplicate_endpoint",
                        "message": translate("errors.push.subscription_exists", locale=locale),
                    },
                )
            existing.p256dh = p256dh
            existing.auth = auth
            existing.user_id = user.id
            existing.user_agent = user_agent or None
            existing.last_seen_at = now
            if existing.created_at is None:
                existing.created_at = now
            existing.topics = topics_copy
            subscription = existing
        else:
            subscription = PushSubscription(
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                user_id=user.id,
                user_agent=user_agent or None,
                last_seen_at=now,
                created_at=now,
                topics=topics_copy,
            )
            db.add(subscription)
        await db.flush()
        await _refresh_user_topic_preferences(db, user_id=user.id)
        await db.commit()
        await db.refresh(subscription)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "duplicate_endpoint",
                "message": translate("errors.push.subscription_exists", locale=locale),
            },
        )

    return _serialize_subscription(subscription)


@router.patch("/subscribe/topics", response_model=PushSubscriptionOut)
async def update_subscription_topics(
    payload: PushSubscriptionTopicsUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> PushSubscriptionOut:
    locale = resolve_locale(request=request, user=user)
    await ensure_push_subscription_schema(db)
    endpoint = payload.endpoint.strip()
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_subscription",
                "message": translate(
                    "notifications.push.validation.endpoint_required", locale=locale
                ),
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
                "message": translate("errors.push.subscription_not_found", locale=locale),
            },
        )

    normalized_topics = await synchronize_user_topics(
        db,
        user_id=user.id,
        topics=payload.topics,
    )
    subscription.topics = list(normalized_topics)
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
    locale = resolve_locale(request=request, user=user)
    await ensure_push_subscription_schema(db)
    endpoint = payload.endpoint.strip()
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_subscription",
                "message": translate(
                    "notifications.push.validation.endpoint_required", locale=locale
                ),
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
                "message": translate("errors.rate_limit.push_unsubscribe", locale=locale),
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
    await db.flush()
    await _refresh_user_topic_preferences(db, user_id=user.id)
    await db.commit()
    return {"ok": True, "removed": True}


@router.get("/topics", response_model=PushTopicsResponse)
async def get_push_topics(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> PushTopicsResponse:
    record = (
        await db.execute(select(UserPushTopic).where(UserPushTopic.user_id == user.id))
    ).scalar_one_or_none()
    allowed = get_allowed_topics(settings)
    topics = sort_topics(
        record.topics if record else [],
        allowed_topics=allowed,
    )
    return PushTopicsResponse(
        allowed=allowed,
        topics=topics,
        has_preferences=record is not None,
        updated_at=getattr(record, "updated_at", None),
    )


@router.post("/test", response_model=SendTestResponse)
async def send_test(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    payload: PushTestRequest | None = None,
) -> SendTestResponse:
    locale = resolve_locale(request=request, user=user)
    await ensure_push_subscription_schema(db)
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "forbidden",
                "message": translate("errors.forbidden", locale=locale),
            },
        )

    vapid_ready = bool(settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY)
    allow_missing_credentials = str(settings.environment).lower() in {
        "test",
        "testing",
    }
    if not vapid_ready and not allow_missing_credentials:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=translate("errors.push.not_configured", locale=locale),
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
                "message": translate("errors.rate_limit.push_test", locale=locale),
                "retry_after": info.retry_after,
            },
        )

    target_id = payload.user_id if payload and payload.user_id else user.id
    target = await db.get(User, target_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "user_not_found",
                "message": translate("errors.users.not_found", locale=locale),
            },
        )

    subscriptions = (
        (
            await db.execute(
                select(PushSubscription)
                .options(
                    selectinload(PushSubscription.user).selectinload(User.push_topic_preferences)
                )
                .where(PushSubscription.user_id == target.id)
            )
        )
        .scalars()
        .all()
    )
    if not subscriptions:
        return SendTestResponse(
            total=0,
            sent=0,
            removed=0,
            failed=0,
            detail=translate("notifications.push.test.no_subscriptions", locale=locale),
        )

    normalized_topic = normalize_topic(payload.topic if payload else None) or "system"
    base_url = payload.url if payload and payload.url else settings.app_base_url or "/"
    body = payload.body if payload else None
    title = (
        payload.title
        if payload and payload.title
        else translate("notifications.push.test.title_default", locale=locale)
    )
    message = {
        "title": title,
        "body": body or translate("notifications.push.test.body_default", locale=locale),
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

    results: list[WebPushResult] = []
    for sub in subscriptions:
        if not subscription_supports_topic(sub, normalized_topic):
            continue
        prepared = prepare_push_payload_for_user(message, getattr(sub, "user", None))
        result = await _deliver_to_subscription(sub, prepared)
        results.append(result)
    summary = _aggregate_results(
        results,
        failure_detail=translate("notifications.push.test_failure", locale=locale),
    )
    logger.info(
        "push.test.summary",
        extra={
            "user_id": user.id,
            "target_user_id": target.id,
            "sent": summary.sent,
            "removed": summary.removed,
            "failed": summary.failed,
        },
    )
    return summary


@router.get("/admin/topics/{user_id}", response_model=AdminUserTopicsResponse)
async def admin_get_user_topics(
    user_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> AdminUserTopicsResponse:
    locale = resolve_locale(request=request, user=user)
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "forbidden",
                "message": translate("errors.forbidden", locale=locale),
            },
        )
    target = (
        await db.execute(
            select(User)
            .options(selectinload(User.push_topic_preferences))
            .where(User.id == user_id)
        )
    ).scalar_one_or_none()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "user_not_found",
                "message": translate("errors.users.not_found", locale=locale),
            },
        )
    record = target.push_topic_preferences
    allowed = get_allowed_topics(settings)
    topics = sort_topics(record.topics if record else [], allowed_topics=allowed)
    return AdminUserTopicsResponse(
        user_id=target.id,
        email=target.email,
        topics=topics,
        allowed_topics=allowed,
        updated_at=getattr(record, "updated_at", None),
    )


@router.put("/admin/topics/{user_id}", response_model=AdminUserTopicsResponse)
async def admin_update_user_topics(
    user_id: int,
    payload: AdminUserTopicsUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> AdminUserTopicsResponse:
    locale = resolve_locale(request=request, user=user)
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "forbidden",
                "message": translate("errors.forbidden", locale=locale),
            },
        )
    target = (
        await db.execute(
            select(User)
            .options(selectinload(User.push_topic_preferences))
            .where(User.id == user_id)
        )
    ).scalar_one_or_none()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "user_not_found",
                "message": translate("errors.users.not_found", locale=locale),
            },
        )
    allowed = get_allowed_topics(settings)
    normalized_topics = await synchronize_user_topics(
        db,
        user_id=target.id,
        topics=payload.topics,
    )
    await db.commit()
    await db.refresh(target, attribute_names=["push_topic_preferences"])
    record = target.push_topic_preferences
    topics = sort_topics(normalized_topics, allowed_topics=allowed)
    return AdminUserTopicsResponse(
        user_id=target.id,
        email=target.email,
        topics=topics,
        allowed_topics=allowed,
        updated_at=getattr(record, "updated_at", None),
    )


@router.post("/admin/disable-user")
async def disable_user_push(
    payload: DisableUserPushRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, int | bool]:
    locale = resolve_locale(request=request, user=user)
    await ensure_push_subscription_schema(db)
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "forbidden",
                "message": translate("errors.forbidden", locale=locale),
            },
        )

    target = await db.get(User, payload.user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "user_not_found",
                "message": translate("errors.users.not_found", locale=locale),
            },
        )

    existing = (
        (await db.execute(select(PushSubscription.id).where(PushSubscription.user_id == target.id)))
        .scalars()
        .all()
    )
    if not existing:
        return {"ok": True, "removed": 0}

    await db.execute(delete(PushSubscription).where(PushSubscription.user_id == target.id))
    await db.commit()
    logger.info(
        "push.admin.disable_all",
        extra={
            "user_id": user.id,
            "target_user_id": target.id,
            "removed": len(existing),
        },
    )
    return {"ok": True, "removed": len(existing)}


@router.post("/broadcast", response_model=SendTestResponse)
async def broadcast(
    data: NotifyBody,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> SendTestResponse:
    locale = resolve_locale(request=request, user=user)
    await ensure_push_subscription_schema(db)
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "forbidden",
                "message": translate("errors.forbidden", locale=locale),
            },
        )

    subscriptions = (
        (
            await db.execute(
                select(PushSubscription).options(
                    selectinload(PushSubscription.user).selectinload(User.push_topic_preferences)
                )
            )
        )
        .scalars()
        .all()
    )

    topic = normalize_topic(data.topic)
    payload = data.model_dump(exclude_none=True)
    if topic:
        payload["topic"] = topic
    else:
        payload.pop("topic", None)

    results: list[WebPushResult] = []
    for subscription in subscriptions:
        if not subscription_supports_topic(subscription, topic):
            continue
        prepared = prepare_push_payload_for_user(payload, getattr(subscription, "user", None))
        results.append(await _deliver_to_subscription(subscription, prepared))

    summary = _aggregate_results(
        results,
        failure_detail=translate("notifications.push.broadcast_failure", locale=locale),
    )
    logger.info(
        "push.broadcast.summary",
        extra={
            "user_id": user.id,
            "total": summary.total,
            "sent": summary.sent,
            "removed": summary.removed,
            "failed": summary.failed,
        },
    )
    return summary


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
legacy_router.add_api_route(
    "/admin/disable-user",
    disable_user_push,
    methods=["POST"],
)
legacy_router.add_api_route(
    "/broadcast",
    broadcast,
    methods=["POST"],
    response_model=SendTestResponse,
)
