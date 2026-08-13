"""Web push notification routes."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.localization import resolve_locale, translate
from app.core.logging import get_logger
from app.core.ratelimit import (
    RateLimitExceeded,
    RateLimitInfo,
    enforce_rate_limit,
    get_default_strategy,
)
from app.core.ssrf import validate_public_https_url, validate_url_not_internal_async
from app.models import PushSubscription, User, UserPushTopic
from app.models.enums import UserRole
from app.schemas.notifications import (
    AdminUserTopicsResponse,
    AdminUserTopicsUpdate,
    DisableUserPushRequest,
    NotifyBody,
    PushSubscriptionDelete,
    PushSubscriptionIn,
    PushSubscriptionOut,
    PushSubscriptionTopicsUpdate,
    PushTestRequest,
    PushTopicsResponse,
    SendTestResponse,
)
from app.services.push_service import deliver_push_to_subscriptions
from app.services.push_topics import (
    get_allowed_topics,
    normalize_topic,
    normalize_topics,
    resolve_topics,
    sort_topics,
    synchronize_user_topics,
)
from app.services.webpush import WebPushResult

logger = get_logger(__name__)

router = APIRouter(prefix="/push", tags=["push"])


def _serialize_subscription(subscription: PushSubscription) -> PushSubscriptionOut:
    topics = normalize_topics(subscription.topics or [])
    created_at = getattr(subscription, "created_at", None)
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


def _aggregate_results(
    results: list[WebPushResult], *, failure_detail: str
) -> SendTestResponse:
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


async def _refresh_user_topic_preferences(
    db: AsyncSession, *, user_id: uuid.UUID
) -> None:
    """
    Synchronize stored user topic preferences with subscription data
    with robust upsert.
    """

    topics_rows = (
        await db.execute(
            select(PushSubscription.topics).where(PushSubscription.user_id == user_id)
        )
    ).scalars()
    aggregated: list[str] = []
    for row in topics_rows:
        if row:
            aggregated.extend(str(item) for item in row if item)
    normalized = sort_topics(aggregated, settings_obj=settings)

    try:
        # Avoid creating multiple topics records for the same user in parallel
        async with db.begin_nested():
            record = (
                await db.execute(
                    select(UserPushTopic).where(UserPushTopic.user_id == user_id)
                )
            ).scalar_one_or_none()

            if normalized:
                topics_copy = list(normalized)
                if record is None:
                    db.add(UserPushTopic(user_id=user_id, topics=topics_copy))
                else:
                    record.topics = topics_copy
            elif record is not None:
                await db.delete(record)
            await db.flush()
    except IntegrityError:
        # Another process might have inserted it between select and flush
        record = (
            await db.execute(
                select(UserPushTopic).where(UserPushTopic.user_id == user_id)
            )
        ).scalar_one_or_none()
        if record:
            if normalized:
                record.topics = list(normalized)
            else:
                await db.delete(record)
            await db.flush()


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
    else:
        try:
            validate_public_https_url(endpoint)
            # Development/test fixtures may use non-resolving provider
            # placeholders, but a hostname that resolves to an internal
            # address is rejected in every environment.
            try:
                await validate_url_not_internal_async(endpoint)
            except ValueError as exc:
                if not (
                    getattr(settings, "is_development", False)
                    and "DNS resolution failed" in str(exc)
                ):
                    raise
        except ValueError:
            errors.append(
                {
                    "field": "endpoint",
                    "message": translate(
                        "notifications.push.validation.endpoint_invalid",
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
                "message": translate(
                    "errors.push.subscription_validation_failed", locale=locale
                ),
                "fields": errors,
            },
        )
    return endpoint, p256dh, auth


@router.get("/vapid-public-key")
# nosec: public_endpoint
async def get_vapid_public_key() -> dict[str, str | None]:
    """Return configured VAPID public key."""
    key = settings.VAPID_PUBLIC_KEY.strip() if settings.VAPID_PUBLIC_KEY else ""
    return {"publicKey": key if key else None}


@router.post("/subscribe", response_model=PushSubscriptionOut)
async def subscribe(
    payload: PushSubscriptionIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> PushSubscriptionOut:
    locale = resolve_locale(request=request, user=user)
    endpoint, p256dh, auth = await _validate_subscription_payload(
        payload, locale=locale
    )

    client_host = request.client.host if request.client else None
    try:
        await enforce_rate_limit(
            identifier=f"user:{user.id}",
            limit=20,
            window_seconds=60,
            strategy=get_default_strategy("push:subscribe:user"),
        )
        if client_host:
            await enforce_rate_limit(
                identifier=f"ip:{client_host}",
                limit=60,
                window_seconds=60,
                strategy=get_default_strategy("push:subscribe:ip"),
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

    now = datetime.now(UTC)
    subscription: PushSubscription | None = None
    max_attempts = 3

    logger.info(
        "push.subscribe.start",
        extra={"endpoint_prefix": endpoint[:50], "user_id": user.id},
    )

    for attempt in range(max_attempts):
        try:
            # First, try to find an existing subscription with this endpoint
            existing = (
                await db.execute(
                    select(PushSubscription).where(
                        PushSubscription.endpoint == endpoint
                    )
                )
            ).scalar_one_or_none()

            logger.debug(
                "push.subscribe.attempt",
                extra={
                    "attempt": attempt + 1,
                    "existing": existing is not None,
                    "endpoint_prefix": endpoint[:50],
                },
            )

            if existing:
                # Transfer ownership or update existing subscription
                payload_topics = payload.topics
                normalized_topics = resolve_topics(payload_topics, existing.topics)
                topics_copy = list(normalized_topics)

                existing.p256dh = p256dh
                existing.auth = auth
                existing.user_id = user.id
                existing.user_agent = user_agent or None
                existing.last_seen_at = now
                if getattr(existing, "created_at", None) is None:
                    existing.created_at = now
                existing.topics = topics_copy
                subscription = existing
            else:
                # Try to create a new one
                normalized_topics = resolve_topics(payload.topics, None)
                subscription = PushSubscription(
                    endpoint=endpoint,
                    p256dh=p256dh,
                    auth=auth,
                    user_id=user.id,
                    user_agent=user_agent or None,
                    last_seen_at=now,
                    created_at=now,
                    topics=list(normalized_topics),
                )
                db.add(subscription)

            await db.flush()
            await _refresh_user_topic_preferences(db, user_id=user.id)
            await db.commit()
            await db.refresh(subscription)
            logger.info(
                "push.subscribe.success",
                extra={
                    "attempt": attempt + 1,
                    "subscription_id": subscription.id,
                    "endpoint_prefix": endpoint[:50],
                },
            )
            break  # Success, exit retry loop
        except IntegrityError as e:
            # Race condition: another request created the subscription concurrently
            logger.warning(
                "push.subscribe.integrity_error",
                extra={
                    "attempt": attempt + 1,
                    "error": str(e)[:200],
                    "endpoint_prefix": endpoint[:50],
                },
            )
            await db.rollback()

            if attempt < max_attempts - 1:
                # Small delay before retry to let the other transaction complete
                await asyncio.sleep(0.05 * (attempt + 1))
                continue

            # Final attempt: try to find and update existing
            existing = (
                await db.execute(
                    select(PushSubscription).where(
                        PushSubscription.endpoint == endpoint
                    )
                )
            ).scalar_one_or_none()

            if existing:
                normalized_topics = resolve_topics(payload.topics, existing.topics)
                existing.p256dh = p256dh
                existing.auth = auth
                existing.user_id = user.id
                existing.user_agent = user_agent or None
                existing.last_seen_at = now
                existing.topics = list(normalized_topics)
                await db.flush()
                await _refresh_user_topic_preferences(db, user_id=user.id)
                await db.commit()
                await db.refresh(existing)
                subscription = existing
                logger.info(
                    "push.subscribe.recovered",
                    extra={
                        "subscription_id": existing.id,
                        "endpoint_prefix": endpoint[:50],
                    },
                )
            else:
                # Log warning but return success - subscription likely exists
                # but we couldn't find it due to transaction isolation
                logger.warning(
                    "push.subscribe.not_found_after_error",
                    extra={"endpoint_prefix": endpoint[:50], "user_id": user.id},
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "duplicate_endpoint",
                        "message": translate(
                            "errors.push.subscription_exists", locale=locale
                        ),
                    },
                ) from e

    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "subscription_failed",
                "message": "Failed to create subscription",
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
                "message": translate(
                    "errors.push.subscription_not_found", locale=locale
                ),
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
            limit=20,
            window_seconds=60,
            strategy=get_default_strategy("push:unsubscribe:user"),
        )
        if client_host:
            await enforce_rate_limit(
                identifier=f"ip:{client_host}",
                limit=60,
                window_seconds=60,
                strategy=get_default_strategy("push:unsubscribe:ip"),
            )
    except RateLimitExceeded as exc:
        info: RateLimitInfo = exc.info
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": translate(
                    "errors.rate_limit.push_unsubscribe", locale=locale
                ),
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
    )


@router.post("/test", response_model=SendTestResponse)
async def send_test(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    payload: PushTestRequest | None = None,
) -> SendTestResponse:
    locale = resolve_locale(request=request, user=user)
    if user.role != UserRole.ADMIN:
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
            limit=5,
            window_seconds=60,
            strategy=get_default_strategy("push:test:user"),
        )
        if client_host:
            await enforce_rate_limit(
                identifier=f"ip:{client_host}",
                limit=15,
                window_seconds=60,
                strategy=get_default_strategy("push:test:ip"),
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
        ) from exc

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
                    selectinload(PushSubscription.user).selectinload(
                        User.push_topic_preferences
                    )
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
        "body": body
        or translate("notifications.push.test.body_default", locale=locale),
        "url": base_url,
    }
    message["topic"] = normalized_topic

    optional_fields = ("tag", "badge", "ttl", "urgency", "actions", "data")
    if payload:
        for field in optional_fields:
            value = getattr(payload, field, None)
            if value is not None:
                message[field] = value

    results = await deliver_push_to_subscriptions(
        subscriptions, message, topic=normalized_topic, concurrency=20
    )
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
    user_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> AdminUserTopicsResponse:
    locale = resolve_locale(request=request, user=user)
    if user.role != UserRole.ADMIN:
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
    user_id: uuid.UUID,
    payload: AdminUserTopicsUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> AdminUserTopicsResponse:
    locale = resolve_locale(request=request, user=user)
    if user.role != UserRole.ADMIN:
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
    if user.role != UserRole.ADMIN:
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
        (
            await db.execute(
                select(PushSubscription.id).where(PushSubscription.user_id == target.id)
            )
        )
        .scalars()
        .all()
    )
    if not existing:
        return {"ok": True, "removed": 0}

    await db.execute(
        delete(PushSubscription).where(PushSubscription.user_id == target.id)
    )
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
    # RZ-33-18: Auth check BEFORE rate limit — prevents unauthenticated users
    # from exhausting the admin's rate-limit budget.
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "forbidden",
                "message": translate("errors.forbidden", locale=locale),
            },
        )

    # RZ-W19-18: rate limit broadcast — max 5 per hour to prevent DB/WebPush saturation
    try:
        await enforce_rate_limit(
            strategy=get_default_strategy(),
            identifier=f"push:broadcast:{user.id}",
            limit=5,
            window_seconds=3600,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": translate("errors.rate_limit.push_broadcast", locale=locale),
                "retry_after": exc.info.retry_after,
            },
        ) from None

    topic = normalize_topic(data.topic)
    payload = data.model_dump(exclude_none=True)
    if topic:
        payload["topic"] = topic
    else:
        payload.pop("topic", None)

    # Stream subscriptions in batches to avoid loading all ORM objects at once.
    # At 10k users × 2 devices each = 20k rows × ~2 KB per object = ~40 MB
    # if loaded as a single query. Batching keeps peak memory bounded at
    # BROADCAST_BATCH_SIZE × ~2 KB regardless of total subscription count.
    _BROADCAST_BATCH_SIZE = 500
    results: list[WebPushResult] = []
    offset = 0

    while True:
        batch = (
            (
                await db.execute(
                    select(PushSubscription)
                    .options(
                        selectinload(PushSubscription.user).selectinload(
                            User.push_topic_preferences
                        )
                    )
                    .order_by(PushSubscription.id)
                    .limit(_BROADCAST_BATCH_SIZE)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        if not batch:
            break

        batch_results = await deliver_push_to_subscriptions(
            batch, payload, topic=topic, concurrency=50
        )
        results.extend(batch_results)
        offset += _BROADCAST_BATCH_SIZE
        # Yield to the event loop between batches so other requests are not starved.
        await asyncio.sleep(0)
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
