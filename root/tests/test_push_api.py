import pytest
from fastapi import HTTPException, Request
from sqlalchemy import select
from starlette.requests import Request

from app.localization import translate
from app.models.models import PushSubscription
from app.routers.notifications import (
    DisableUserPushRequest,
    NotifyBody,
    broadcast,
    disable_user_push,
    send_test,
)
from app.services.webpush import WebPushResult


def _make_request(path: str) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [],
        "query_string": b"",
        "client": ("testclient", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


@pytest.mark.anyio
async def test_push_test_returns_aggregated_stats(
    db_session,
    user_factory,
    monkeypatch,
) -> None:
    user = await user_factory(role="admin")
    subscriptions = [
        PushSubscription(
            endpoint=f"https://example.com/sub-{idx}",
            p256dh=f"key-{idx}",
            auth=f"auth-{idx}",
            user_id=user.id,
            topics=["system"],
        )
        for idx in range(3)
    ]
    db_session.add_all(subscriptions)
    await db_session.commit()

    results = iter(
        [
            WebPushResult(
                subscription_id=subscriptions[0].id,
                endpoint=subscriptions[0].endpoint,
                user_id=user.id,
                status="sent",
            ),
            WebPushResult(
                subscription_id=subscriptions[1].id,
                endpoint=subscriptions[1].endpoint,
                user_id=user.id,
                status="gone",
                status_code=410,
            ),
            WebPushResult(
                subscription_id=subscriptions[2].id,
                endpoint=subscriptions[2].endpoint,
                user_id=user.id,
                status="error",
                status_code=500,
                error="boom",
            ),
        ]
    )

    async def _fake_deliver(*args, **kwargs):
        return next(results)

    monkeypatch.setattr(
        "app.routers.notifications._deliver_to_subscription", _fake_deliver
    )

    request = _make_request("/push/test")
    response = await send_test(request=request, db=db_session, user=user, payload=None)
    assert response.model_dump() == {
        "total": 3,
        "sent": 1,
        "removed": 1,
        "failed": 1,
        "detail": None,
    }


@pytest.mark.anyio
async def test_push_broadcast_reports_failures(
    db_session,
    user_factory,
    monkeypatch,
) -> None:
    admin = await user_factory(role="admin")
    subs = [
        PushSubscription(
            endpoint=f"https://example.com/admin-{idx}",
            p256dh=f"key-{idx}",
            auth=f"auth-{idx}",
            user_id=admin.id,
            topics=["news"],
        )
        for idx in range(2)
    ]
    db_session.add_all(subs)
    await db_session.commit()

    async def _fail_deliver(*args, **kwargs):
        return WebPushResult(
            subscription_id=subs[0].id,
            endpoint=subs[0].endpoint,
            user_id=admin.id,
            status="error",
            status_code=503,
            error="Service Unavailable",
        )

    monkeypatch.setattr(
        "app.routers.notifications._deliver_to_subscription", _fail_deliver
    )

    payload = NotifyBody(title="System", body="Maintenance", url="/")
    response = await broadcast(
        data=payload,
        request=_make_request("/push/broadcast"),
        db=db_session,
        user=admin,
    )
    assert response.model_dump() == {
        "total": 2,
        "sent": 0,
        "removed": 0,
        "failed": 2,
        "detail": translate("notifications.push.broadcast_failure"),
    }


@pytest.mark.anyio
async def test_admin_disable_user_push_removes_subscriptions(
    db_session, user_factory
) -> None:
    admin = await user_factory(role="admin")
    target = await user_factory()
    other_user = await user_factory()
    subscriptions = [
        PushSubscription(
            endpoint=f"https://example.com/target-{idx}",
            p256dh=f"key-{idx}",
            auth=f"auth-{idx}",
            user_id=target.id,
            topics=["news"],
        )
        for idx in range(2)
    ] + [
        PushSubscription(
            endpoint="https://example.com/other",
            p256dh="key-other",
            auth="auth-other",
            user_id=other_user.id,
            topics=["news"],
        )
    ]
    db_session.add_all(subscriptions)
    await db_session.commit()

    payload = DisableUserPushRequest(user_id=target.id)
    response = await disable_user_push(
        payload=payload,
        request=_make_request("/push/admin/disable-user"),
        db=db_session,
        user=admin,
    )

    assert response == {"ok": True, "removed": 2}
    remaining = (
        (
            await db_session.execute(
                select(PushSubscription).where(PushSubscription.user_id == target.id)
            )
        )
        .scalars()
        .all()
    )
    assert remaining == []
    others = (
        (
            await db_session.execute(
                select(PushSubscription).where(
                    PushSubscription.user_id == other_user.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(others) == 1


@pytest.mark.anyio
async def test_admin_disable_user_push_requires_admin(db_session, user_factory) -> None:
    requester = await user_factory()
    target = await user_factory()
    payload = DisableUserPushRequest(user_id=target.id)
    with pytest.raises(HTTPException) as exc:
        await disable_user_push(
            payload=payload,
            request=_make_request("/push/admin/disable-user"),
            db=db_session,
            user=requester,
        )
    assert exc.value.status_code == 403


@pytest.mark.anyio
async def test_admin_disable_user_push_missing_user(db_session, user_factory) -> None:
    admin = await user_factory(role="admin")
    payload = DisableUserPushRequest(user_id=9999)
    with pytest.raises(HTTPException) as exc:
        await disable_user_push(
            payload=payload,
            request=_make_request("/push/admin/disable-user"),
            db=db_session,
            user=admin,
        )
    assert exc.value.status_code == 404
