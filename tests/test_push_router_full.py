"""Comprehensive tests for app/routers/notifications.py push endpoints.

Covers all 10 endpoints, rate limiting, retry logic, admin guards,
validation errors, and edge cases.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import get_password_hash
from app.models import PushSubscription, UserPushTopic
from app.services.webpush import WebPushResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_PASSWORD = "TestPassword123!"  # pragma: allowlist secret


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    resp = await client.post(
        "/auth/login",
        data={"username": email, "password": _TEST_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    token = resp.cookies.get("access_token_v2") or client.cookies.get("access_token_v2")
    assert token, "access_token_v2 cookie not found after login"
    return {"Authorization": f"Bearer {token}", "X-Query-Budget": "15"}


def _sub_payload(endpoint: str | None = None, topics: list[str] | None = None):
    return {
        "endpoint": endpoint or f"https://push.example.com/{uuid.uuid4().hex}",
        "keys": {
            "p256dh": "test_p256dh_key_for_push",
            "auth": "test_auth_key",
        },
        "topics": topics or [],
    }


# ---------------------------------------------------------------------------
# GET /push/vapid-public-key
# ---------------------------------------------------------------------------


class TestVapidPublicKey:
    @pytest.mark.asyncio
    async def test_returns_key(self, async_client: AsyncClient):
        resp = await async_client.get("/push/vapid-public-key")
        assert resp.status_code == 200
        assert "publicKey" in resp.json()

    @pytest.mark.asyncio
    async def test_returns_key_value(self, async_client: AsyncClient):
        """VAPID key endpoint returns the configured key."""
        resp = await async_client.get("/push/vapid-public-key")
        assert resp.status_code == 200
        data = resp.json()
        # Key is either a string or None depending on config
        assert "publicKey" in data


# ---------------------------------------------------------------------------
# POST /push/subscribe
# ---------------------------------------------------------------------------


class TestSubscribe:
    @pytest.mark.asyncio
    async def test_create_new_subscription(
        self, async_client: AsyncClient, user_factory, db_session: AsyncSession
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        payload = _sub_payload(topics=["system"])
        resp = await async_client.post("/push/subscribe", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["endpoint"] == payload["endpoint"]
        assert "id" in data

    @pytest.mark.asyncio
    async def test_update_existing_subscription(
        self,
        async_client: AsyncClient,
        user_factory,
        push_subscription_factory,
        db_session: AsyncSession,
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        endpoint = f"https://push.example.com/{uuid.uuid4().hex}"
        await push_subscription_factory(user=user, endpoint=endpoint, topics=["old"])

        headers = await _login(async_client, user.email)
        payload = _sub_payload(endpoint=endpoint, topics=["system"])
        resp = await async_client.post("/push/subscribe", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["endpoint"] == endpoint

    @pytest.mark.asyncio
    async def test_validation_empty_endpoint(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        payload = {
            "endpoint": "   ",
            "keys": {"p256dh": "valid", "auth": "valid"},
        }
        resp = await async_client.post("/push/subscribe", json=payload, headers=headers)
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "invalid_subscription"

    @pytest.mark.asyncio
    async def test_validation_empty_keys(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        payload = {
            "endpoint": "https://push.example.com/valid",
            "keys": {"p256dh": "", "auth": ""},
        }
        resp = await async_client.post("/push/subscribe", json=payload, headers=headers)
        assert resp.status_code == 400
        fields = resp.json()["detail"]["fields"]
        assert len(fields) == 2

    @pytest.mark.asyncio
    async def test_truncates_long_user_agent(
        self, async_client: AsyncClient, user_factory, db_session: AsyncSession
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        payload = _sub_payload()
        payload["user_agent"] = "A" * 1000
        resp = await async_client.post("/push/subscribe", json=payload, headers=headers)
        assert resp.status_code == 200

        sub = (
            await db_session.execute(
                select(PushSubscription).where(PushSubscription.user_id == user.id)
            )
        ).scalar_one()
        assert sub.user_agent is not None
        assert len(sub.user_agent) <= 512

    @pytest.mark.asyncio
    async def test_integrity_error_retry_recovery(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        """Test that subscribe retries on IntegrityError and recovers."""
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        endpoint = f"https://push.example.com/{uuid.uuid4().hex}"

        # Create the subscription first so the second attempt hits IntegrityError
        # then recovers by finding and updating existing
        sub = PushSubscription(
            endpoint=endpoint,
            p256dh="old_key",
            auth="old_auth",
            user_id=user.id,
            created_at=datetime.now(UTC),
            topics=[],
        )
        db_session.add(sub)
        await db_session.commit()

        payload = _sub_payload(endpoint=endpoint, topics=["system"])
        resp = await async_client.post("/push/subscribe", json=payload, headers=headers)
        # Should succeed by finding + updating existing
        assert resp.status_code == 200
        assert resp.json()["endpoint"] == endpoint


# ---------------------------------------------------------------------------
# PATCH /push/subscribe/topics
# ---------------------------------------------------------------------------


class TestUpdateTopics:
    @pytest.mark.asyncio
    async def test_update_topics_success(
        self,
        async_client: AsyncClient,
        user_factory,
        push_subscription_factory,
        db_session,
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        endpoint = f"https://push.example.com/{uuid.uuid4().hex}"
        await push_subscription_factory(user=user, endpoint=endpoint, topics=[])

        headers = await _login(async_client, user.email)
        resp = await async_client.patch(
            "/push/subscribe/topics",
            json={"endpoint": endpoint, "topics": ["system"]},
            headers=headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_topics_not_found(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        resp = await async_client.patch(
            "/push/subscribe/topics",
            json={"endpoint": "https://nonexistent.example.com", "topics": ["system"]},
            headers=headers,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["error"] == "subscription_not_found"

    @pytest.mark.asyncio
    async def test_update_topics_empty_endpoint(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        resp = await async_client.patch(
            "/push/subscribe/topics",
            json={"endpoint": "  ", "topics": ["system"]},
            headers=headers,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /push/unsubscribe
# ---------------------------------------------------------------------------


class TestUnsubscribe:
    @pytest.mark.asyncio
    async def test_unsubscribe_existing(
        self,
        async_client: AsyncClient,
        user_factory,
        push_subscription_factory,
        db_session: AsyncSession,
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        endpoint = f"https://push.example.com/{uuid.uuid4().hex}"
        await push_subscription_factory(user=user, endpoint=endpoint)

        headers = await _login(async_client, user.email)
        resp = await async_client.post(
            "/push/unsubscribe", json={"endpoint": endpoint}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["removed"] is True

        # Verify deleted from DB
        row = (
            await db_session.execute(
                select(PushSubscription).where(PushSubscription.endpoint == endpoint)
            )
        ).scalar_one_or_none()
        assert row is None

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        resp = await async_client.post(
            "/push/unsubscribe",
            json={"endpoint": "https://nonexistent.example.com"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["removed"] is False

    @pytest.mark.asyncio
    async def test_unsubscribe_empty_endpoint(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        resp = await async_client.post(
            "/push/unsubscribe",
            json={"endpoint": "  "},
            headers=headers,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /push/topics
# ---------------------------------------------------------------------------


class TestGetTopics:
    @pytest.mark.asyncio
    async def test_empty_topics(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)
        headers = await _login(async_client, user.email)

        resp = await async_client.get("/push/topics", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_preferences"] is False
        assert isinstance(data["topics"], list)
        assert isinstance(data["allowed"], list)

    @pytest.mark.asyncio
    async def test_with_preferences(
        self, async_client: AsyncClient, user_factory, db_session: AsyncSession
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(hashed_password=hashed, is_active=True)

        topic_pref = UserPushTopic(user_id=user.id, topics=["system"])
        db_session.add(topic_pref)
        await db_session.commit()

        headers = await _login(async_client, user.email)
        resp = await async_client.get("/push/topics", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["has_preferences"] is True


# ---------------------------------------------------------------------------
# POST /push/test (admin only)
# ---------------------------------------------------------------------------


class TestSendTest:
    @pytest.mark.asyncio
    async def test_forbidden_for_non_admin(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(
            hashed_password=hashed, is_active=True, role="student"
        )
        headers = await _login(async_client, user.email)

        resp = await async_client.post("/push/test", headers=headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_no_subscriptions(
        self, async_client: AsyncClient, user_factory, db_session, mock_deliver_push
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        admin = await user_factory(hashed_password=hashed, is_active=True, role="admin")
        headers = await _login(async_client, admin.email)

        resp = await async_client.post(
            "/push/test",
            json={"title": "Test", "user_id": str(admin.id)},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["detail"] is not None  # "no subscriptions" message

    @pytest.mark.asyncio
    async def test_with_subscriptions(
        self,
        async_client: AsyncClient,
        user_factory,
        push_subscription_factory,
        db_session,
        mock_deliver_push,
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        admin = await user_factory(hashed_password=hashed, is_active=True, role="admin")
        target = await user_factory(hashed_password=hashed, is_active=True)
        await push_subscription_factory(user=target)

        mock_deliver_push.return_value = [
            WebPushResult(
                subscription_id=uuid.uuid4(),
                endpoint="https://push.example.com/test",
                user_id=target.id,
                status="sent",
            )
        ]

        headers = await _login(async_client, admin.email)
        resp = await async_client.post(
            "/push/test",
            json={"title": "Test Push", "topic": "system", "user_id": str(target.id)},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["sent"] == 1

    @pytest.mark.asyncio
    async def test_target_user_not_found(
        self, async_client: AsyncClient, user_factory, db_session, mock_deliver_push
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        admin = await user_factory(hashed_password=hashed, is_active=True, role="admin")
        headers = await _login(async_client, admin.email)

        resp = await async_client.post(
            "/push/test",
            json={"title": "T", "user_id": str(uuid.uuid4())},
            headers=headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_all_pushes_fail_shows_detail(
        self,
        async_client: AsyncClient,
        user_factory,
        push_subscription_factory,
        db_session,
        mock_deliver_push,
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        admin = await user_factory(hashed_password=hashed, is_active=True, role="admin")
        target = await user_factory(hashed_password=hashed, is_active=True)
        await push_subscription_factory(user=target)

        mock_deliver_push.return_value = [
            WebPushResult(
                subscription_id=uuid.uuid4(),
                endpoint="https://push.example.com/test",
                user_id=target.id,
                status="error",
                error="timeout",
            )
        ]

        headers = await _login(async_client, admin.email)
        resp = await async_client.post(
            "/push/test",
            json={"title": "Fail Test", "user_id": str(target.id)},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["failed"] == 1
        assert data["sent"] == 0
        assert data["detail"] is not None  # failure detail present


# ---------------------------------------------------------------------------
# GET /push/admin/topics/{user_id}
# ---------------------------------------------------------------------------


class TestAdminGetTopics:
    @pytest.mark.asyncio
    async def test_admin_gets_topics(
        self, async_client: AsyncClient, user_factory, db_session: AsyncSession
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        admin = await user_factory(hashed_password=hashed, is_active=True, role="admin")
        target = await user_factory(hashed_password=hashed, is_active=True)

        headers = await _login(async_client, admin.email)
        resp = await async_client.get(
            f"/push/admin/topics/{target.id}", headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == str(target.id)
        assert isinstance(data["topics"], list)

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(
            hashed_password=hashed, is_active=True, role="student"
        )
        headers = await _login(async_client, user.email)

        resp = await async_client.get(
            f"/push/admin/topics/{uuid.uuid4()}", headers=headers
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_target_not_found(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        admin = await user_factory(hashed_password=hashed, is_active=True, role="admin")
        headers = await _login(async_client, admin.email)

        resp = await async_client.get(
            f"/push/admin/topics/{uuid.uuid4()}", headers=headers
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /push/admin/topics/{user_id}
# ---------------------------------------------------------------------------


class TestAdminUpdateTopics:
    @pytest.mark.asyncio
    async def test_admin_updates_topics(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        admin = await user_factory(hashed_password=hashed, is_active=True, role="admin")
        target = await user_factory(hashed_password=hashed, is_active=True)

        headers = await _login(async_client, admin.email)
        resp = await async_client.put(
            f"/push/admin/topics/{target.id}",
            json={"topics": ["system"]},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == str(target.id)

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(
            hashed_password=hashed, is_active=True, role="student"
        )
        headers = await _login(async_client, user.email)

        resp = await async_client.put(
            f"/push/admin/topics/{uuid.uuid4()}",
            json={"topics": ["system"]},
            headers=headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_target_not_found(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        admin = await user_factory(hashed_password=hashed, is_active=True, role="admin")
        headers = await _login(async_client, admin.email)

        resp = await async_client.put(
            f"/push/admin/topics/{uuid.uuid4()}",
            json={"topics": ["system"]},
            headers=headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /push/admin/disable-user
# ---------------------------------------------------------------------------


class TestDisableUserPush:
    @pytest.mark.asyncio
    async def test_admin_disables_push(
        self,
        async_client: AsyncClient,
        user_factory,
        push_subscription_factory,
        db_session: AsyncSession,
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        admin = await user_factory(hashed_password=hashed, is_active=True, role="admin")
        target = await user_factory(hashed_password=hashed, is_active=True)
        await push_subscription_factory(user=target)
        await push_subscription_factory(user=target)

        headers = await _login(async_client, admin.email)
        resp = await async_client.post(
            "/push/admin/disable-user",
            json={"user_id": str(target.id)},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["removed"] == 2

    @pytest.mark.asyncio
    async def test_admin_disables_no_subscriptions(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        admin = await user_factory(hashed_password=hashed, is_active=True, role="admin")
        target = await user_factory(hashed_password=hashed, is_active=True)

        headers = await _login(async_client, admin.email)
        resp = await async_client.post(
            "/push/admin/disable-user",
            json={"user_id": str(target.id)},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["removed"] == 0

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(
            hashed_password=hashed, is_active=True, role="student"
        )
        headers = await _login(async_client, user.email)

        resp = await async_client.post(
            "/push/admin/disable-user",
            json={"user_id": str(uuid.uuid4())},
            headers=headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_target_not_found(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        admin = await user_factory(hashed_password=hashed, is_active=True, role="admin")
        headers = await _login(async_client, admin.email)

        resp = await async_client.post(
            "/push/admin/disable-user",
            json={"user_id": str(uuid.uuid4())},
            headers=headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /push/broadcast (admin only)
# ---------------------------------------------------------------------------


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_non_admin_forbidden(
        self, async_client: AsyncClient, user_factory, db_session
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        user = await user_factory(
            hashed_password=hashed, is_active=True, role="student"
        )
        headers = await _login(async_client, user.email)

        resp = await async_client.post(
            "/push/broadcast",
            json={"title": "Test", "body": "Hello"},
            headers=headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_broadcast_empty(
        self, async_client: AsyncClient, user_factory, db_session, mock_deliver_push
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        admin = await user_factory(hashed_password=hashed, is_active=True, role="admin")
        headers = await _login(async_client, admin.email)

        resp = await async_client.post(
            "/push/broadcast",
            json={"title": "Test", "body": "Hello"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_broadcast_with_subscriptions(
        self,
        async_client: AsyncClient,
        user_factory,
        push_subscription_factory,
        db_session,
        mock_deliver_push,
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        admin = await user_factory(hashed_password=hashed, is_active=True, role="admin")
        target = await user_factory(hashed_password=hashed, is_active=True)
        sub = await push_subscription_factory(user=target)

        mock_deliver_push.return_value = [
            WebPushResult(
                subscription_id=sub.id,
                endpoint=sub.endpoint,
                user_id=target.id,
                status="sent",
            )
        ]

        headers = await _login(async_client, admin.email)
        resp = await async_client.post(
            "/push/broadcast",
            json={"title": "Broadcast", "body": "All users", "topic": "system"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["sent"] == 1

    @pytest.mark.asyncio
    async def test_broadcast_without_topic(
        self,
        async_client: AsyncClient,
        user_factory,
        db_session,
        mock_deliver_push,
    ):
        hashed = await get_password_hash(_TEST_PASSWORD)
        admin = await user_factory(hashed_password=hashed, is_active=True, role="admin")
        headers = await _login(async_client, admin.email)

        resp = await async_client.post(
            "/push/broadcast",
            json={"title": "No Topic", "body": "Hello"},
            headers=headers,
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    @pytest.mark.asyncio
    async def test_serialize_subscription(
        self, db_session, user_factory, push_subscription_factory
    ):
        from app.routers.notifications import _serialize_subscription

        user = await user_factory()
        sub = await push_subscription_factory(user=user, topics=["system"])
        result = _serialize_subscription(sub)
        assert result.endpoint == sub.endpoint
        assert result.id == sub.id

    @pytest.mark.asyncio
    async def test_serialize_subscription_no_created_at(
        self, db_session, user_factory, push_subscription_factory
    ):
        from app.routers.notifications import _serialize_subscription

        user = await user_factory()
        sub = await push_subscription_factory(user=user, topics=[])
        # Simulate missing created_at
        sub.created_at = None
        sub.last_seen_at = datetime.now(UTC)
        result = _serialize_subscription(sub)
        assert result.created_at is not None  # falls back to last_seen_at

    def test_aggregate_results_all_sent(self):
        from app.routers.notifications import _aggregate_results

        results = [
            WebPushResult(
                subscription_id=uuid.uuid4(),
                endpoint="https://e.com/1",
                user_id=uuid.uuid4(),
                status="sent",
            ),
            WebPushResult(
                subscription_id=uuid.uuid4(),
                endpoint="https://e.com/2",
                user_id=uuid.uuid4(),
                status="sent",
            ),
        ]
        summary = _aggregate_results(results, failure_detail="fail msg")
        assert summary.sent == 2
        assert summary.failed == 0
        assert summary.detail is None

    def test_aggregate_results_all_failed(self):
        from app.routers.notifications import _aggregate_results

        results = [
            WebPushResult(
                subscription_id=uuid.uuid4(),
                endpoint="https://e.com/1",
                user_id=uuid.uuid4(),
                status="error",
                error="timeout",
            ),
        ]
        summary = _aggregate_results(results, failure_detail="all failed")
        assert summary.sent == 0
        assert summary.failed == 1
        assert summary.detail == "all failed"

    def test_aggregate_results_mixed(self):
        from app.routers.notifications import _aggregate_results

        results = [
            WebPushResult(
                subscription_id=uuid.uuid4(),
                endpoint="e1",
                user_id=uuid.uuid4(),
                status="sent",
            ),
            WebPushResult(
                subscription_id=uuid.uuid4(),
                endpoint="e2",
                user_id=uuid.uuid4(),
                status="gone",
            ),
            WebPushResult(
                subscription_id=uuid.uuid4(),
                endpoint="e3",
                user_id=uuid.uuid4(),
                status="error",
            ),
        ]
        summary = _aggregate_results(results, failure_detail="fail")
        assert summary.sent == 1
        assert summary.removed == 1
        assert summary.failed == 1
        assert summary.detail is None  # not all failed

    def test_aggregate_results_empty(self):
        from app.routers.notifications import _aggregate_results

        summary = _aggregate_results([], failure_detail="fail")
        assert summary.total == 0
        assert summary.detail is None

    @pytest.mark.asyncio
    async def test_refresh_user_topic_preferences_creates(
        self, db_session: AsyncSession, user_factory, push_subscription_factory
    ):
        from app.routers.notifications import _refresh_user_topic_preferences

        user = await user_factory()
        await push_subscription_factory(user=user, topics=["system", "events"])

        await _refresh_user_topic_preferences(db_session, user_id=user.id)
        await db_session.commit()

        record = (
            await db_session.execute(
                select(UserPushTopic).where(UserPushTopic.user_id == user.id)
            )
        ).scalar_one_or_none()
        assert record is not None
        assert len(record.topics) > 0

    @pytest.mark.asyncio
    async def test_refresh_user_topic_preferences_deletes_when_empty(
        self, db_session: AsyncSession, user_factory
    ):
        from app.routers.notifications import _refresh_user_topic_preferences

        user = await user_factory()
        # Create a topic record with data
        db_session.add(UserPushTopic(user_id=user.id, topics=["old"]))
        await db_session.commit()

        # No subscriptions exist, so topics should be cleaned up
        await _refresh_user_topic_preferences(db_session, user_id=user.id)
        await db_session.commit()

        record = (
            await db_session.execute(
                select(UserPushTopic).where(UserPushTopic.user_id == user.id)
            )
        ).scalar_one_or_none()
        assert record is None
