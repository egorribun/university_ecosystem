"""Integration tests for web push notification routes."""

from __future__ import annotations

import json
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from pywebpush import WebPushException
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.auth.security import get_password_hash
from app.core.config import settings
from app.models.models import PushSubscription
from app.routers.notifications import _serialize_subscription
from app.services import webpush as webpush_module


@pytest.fixture
def _configured_webpush_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for cached in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "WEBPUSH_SUBJECT"):
        settings.__dict__.pop(cached, None)
    monkeypatch.setattr(settings, "vapid_public_key", "test-public-key")
    monkeypatch.setattr(settings, "vapid_private_key", "test-private-key")
    monkeypatch.setattr(settings, "app_base_url", "https://example.test")
    yield
    for cached in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "WEBPUSH_SUBJECT"):
        settings.__dict__.pop(cached, None)


@pytest.fixture
def _sync_session_factory(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    url = make_url(settings.database_url)
    driver = url.drivername
    if "+aiosqlite" in driver:
        url = url.set(drivername=driver.replace("+aiosqlite", ""))
    elif driver.endswith("+asyncpg"):
        url = url.set(drivername="postgresql")
    engine = create_engine(str(url))
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(webpush_module, "_Session", SessionLocal)
    try:
        yield
    finally:
        engine.dispose()


async def _create_user_and_token(
    async_client: AsyncClient,
    user_factory,
    password: str = "StrongP@ssw0rd!",
    *,
    role: str = "student",
):
    hashed = get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True, role=role)
    response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return user, headers


@pytest.mark.anyio
async def test_subscribe_persists_subscription(
    async_client: AsyncClient,
    user_factory,
    db_session,
    _configured_webpush_settings,
):
    user, headers = await _create_user_and_token(async_client, user_factory)

    payload = {
        "endpoint": "https://push.example.test/sub-1",
        "keys": {"p256dh": "key-1", "auth": "auth-1"},
        "topics": ["System", "news"],
        "user_agent": "TestAgent/1.0",
    }

    response = await async_client.post(
        "/push/subscribe",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["endpoint"] == payload["endpoint"]
    assert body["user_id"] == user.id
    assert body["topics"] == ["system", "news"]
    assert body["user_agent"] == payload["user_agent"]
    assert body["last_seen_at"] is not None
    assert body["updated_at"] == body["last_seen_at"]

    stored = (
        await db_session.execute(
            select(PushSubscription).where(
                PushSubscription.endpoint == payload["endpoint"]
            )
        )
    ).scalar_one()
    assert stored.user_id == user.id
    assert stored.p256dh == payload["keys"]["p256dh"]
    assert stored.auth == payload["keys"]["auth"]
    assert stored.topics == ["system", "news"]


def test_serialize_subscription_handles_missing_created_at():
    legacy = SimpleNamespace(
        id=1,
        user_id=2,
        endpoint="https://example.test/legacy",
        p256dh="p256",
        auth="auth",
        created_at=None,
        user_agent="UA/1.0",
        last_seen_at=None,
        topics=["system"],
    )

    result = _serialize_subscription(legacy)

    assert result.created_at is not None
    assert result.user_agent == "UA/1.0"


@pytest.mark.anyio
async def test_unsubscribe_removes_subscription(
    async_client: AsyncClient,
    user_factory,
    db_session,
    _configured_webpush_settings,
):
    _user, headers = await _create_user_and_token(
        async_client, user_factory, role="admin"
    )
    endpoint = "https://push.example.test/remove-me"
    payload = {
        "endpoint": endpoint,
        "keys": {"p256dh": "key-2", "auth": "auth-2"},
        "topics": ["system"],
    }
    create_response = await async_client.post(
        "/push/subscribe",
        json=payload,
        headers=headers,
    )
    assert create_response.status_code == 200

    response = await async_client.post(
        "/push/unsubscribe",
        json={"endpoint": endpoint},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "removed": True}

    remaining = (
        (
            await db_session.execute(
                select(PushSubscription).where(PushSubscription.endpoint == endpoint)
            )
        )
        .scalars()
        .all()
    )
    assert remaining == []

    # Deleting again should still return 204 and keep database clean.
    second = await async_client.post(
        "/push/unsubscribe",
        json={"endpoint": endpoint},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json() == {"ok": True, "removed": False}


class _WebPushStub:
    def __init__(self) -> None:
        self.behavior: dict[str, object] = {}
        self.calls: list[dict[str, object]] = []

    def set_result(self, endpoint: str, result: object) -> None:
        self.behavior[endpoint] = result

    def __call__(
        self,
        *,
        subscription_info: dict,
        data: str,
        vapid_private_key: str,
        vapid_claims: dict,
        headers: dict,
        ttl: int,
    ) -> None:
        endpoint = subscription_info["endpoint"]
        self.calls.append(
            {
                "endpoint": endpoint,
                "data": json.loads(data),
                "headers": headers,
                "ttl": ttl,
            }
        )
        outcome = self.behavior.get(endpoint)
        if isinstance(outcome, Exception):
            raise outcome


def _make_gone_exception(status_code: int) -> WebPushException:
    class _Response:
        def __init__(self, code: int) -> None:
            self.status_code = code

    return WebPushException(f"{status_code} gone", response=_Response(status_code))


@pytest.mark.anyio
async def test_send_test_filters_and_cleans_subscriptions(
    async_client: AsyncClient,
    user_factory,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    _configured_webpush_settings,
    _sync_session_factory,
):
    _user, headers = await _create_user_and_token(
        async_client, user_factory, role="admin"
    )

    stub = _WebPushStub()
    monkeypatch.setattr(webpush_module, "webpush", stub)

    ok_endpoint = "https://push.example.test/ok"
    gone_410_endpoint = "https://push.example.test/gone-410"
    gone_404_endpoint = "https://push.example.test/gone-404"
    news_only_endpoint = "https://push.example.test/news"

    stub.set_result(gone_410_endpoint, _make_gone_exception(410))
    stub.set_result(gone_404_endpoint, _make_gone_exception(404))

    async def _subscribe(endpoint: str, topics: list[str]) -> None:
        payload = {
            "endpoint": endpoint,
            "keys": {"p256dh": f"key-{endpoint[-3:]}", "auth": f"auth-{endpoint[-3:]}"},
            "topics": topics,
        }
        resp = await async_client.post(
            "/push/subscribe",
            json=payload,
            headers=headers,
        )
        assert resp.status_code == 200

    await _subscribe(ok_endpoint, ["system"])
    await _subscribe(gone_410_endpoint, ["system", "news"])
    await _subscribe(gone_404_endpoint, ["system"])
    await _subscribe(news_only_endpoint, ["news"])

    response = await async_client.post("/push/test", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "total": 3,
        "sent": 1,
        "removed": 2,
        "failed": 0,
        "detail": None,
    }

    called_endpoints = {call["endpoint"] for call in stub.calls}
    assert called_endpoints == {ok_endpoint, gone_410_endpoint, gone_404_endpoint}

    remaining = (
        (
            await db_session.execute(
                select(PushSubscription).order_by(PushSubscription.endpoint)
            )
        )
        .scalars()
        .all()
    )
    remaining_endpoints = {sub.endpoint for sub in remaining}
    assert remaining_endpoints == {ok_endpoint, news_only_endpoint}

    success_sub = next(sub for sub in remaining if sub.endpoint == ok_endpoint)
    assert success_sub.last_seen_at is not None
    assert all(call["headers"].get("Topic") == "system" for call in stub.calls)
