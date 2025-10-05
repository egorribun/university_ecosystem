import pytest

from app.api.push import NotifyBody, broadcast, send_test
from app.models.models import PushSubscription
from app.services.webpush import WebPushResult


@pytest.mark.anyio
async def test_push_test_returns_aggregated_stats(
    db_session,
    user_factory,
    monkeypatch,
) -> None:
    user = await user_factory()
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

    monkeypatch.setattr("app.api.push._deliver_to_subscription", _fake_deliver)

    response = await send_test(data=None, session=db_session, user=user)
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

    monkeypatch.setattr("app.api.push._deliver_to_subscription", _fail_deliver)

    payload = NotifyBody(title="System", body="Maintenance", url="/")
    response = await broadcast(data=payload, session=db_session, user=admin)
    assert response.model_dump() == {
        "total": 2,
        "sent": 0,
        "removed": 0,
        "failed": 2,
        "detail": "Не удалось отправить уведомления",
    }
