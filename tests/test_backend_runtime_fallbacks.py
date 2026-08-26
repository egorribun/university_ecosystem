"""Cross-cutting backend fallback and error-path tests."""

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import Response
from sqlalchemy.exc import IntegrityError

# Targets
import app.api.auth.mfa as mfa_api
import app.api.notifications as notifications_api
import app.api.spotify as spotify_api
import app.api.users as users_api
import app.api.websocket as websocket_api
import app.core.database as database_core
import app.core.metrics as metrics_core
import app.core.observability as observability_core
import app.graphql.extensions as graphql_extensions
import app.routers.notifications as push_router


# Helper to mock Dishka container on request
def setup_dishka_mock(request, db, audit):
    container = MagicMock()

    async def mock_get(dep_type, *args, **kwargs):
        if "AuditService" in str(dep_type):
            return audit
        return db

    container.get = mock_get
    request.state.dishka_container = container


# ----------------------------------------------------
# 1. app/api/auth/mfa.py
# ----------------------------------------------------


@pytest.mark.asyncio
async def test_mfa_delete_pending_totp_enrollment_errors():
    db = AsyncMock()
    audit = MagicMock()
    request = MagicMock()
    setup_dishka_mock(request, db, audit)
    user = MagicMock()
    user.id = uuid.uuid4()

    # 1. Enrollment not found
    db.get = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await mfa_api.delete_pending_totp_enrollment(
            enrollment_id=uuid.uuid4(), request=request, db=db, user=user
        )
    assert exc.value.status_code == 404

    # 2. Enrollment belongs to different user
    other_enrollment = MagicMock()
    other_enrollment.user_id = uuid.uuid4()
    db.get = AsyncMock(return_value=other_enrollment)
    with pytest.raises(HTTPException) as exc:
        await mfa_api.delete_pending_totp_enrollment(
            enrollment_id=uuid.uuid4(), request=request, db=db, user=user
        )
    assert exc.value.status_code == 404

    # 3. Enrollment already confirmed
    confirmed_enrollment = MagicMock()
    confirmed_enrollment.user_id = user.id
    confirmed_enrollment.confirmed_at = datetime.now(UTC)
    confirmed_enrollment.revoked_at = None
    db.get = AsyncMock(return_value=confirmed_enrollment)
    with pytest.raises(HTTPException) as exc:
        await mfa_api.delete_pending_totp_enrollment(
            enrollment_id=uuid.uuid4(), request=request, db=db, user=user
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_mfa_confirm_totp_enrollment_failure():
    db = AsyncMock()
    audit = MagicMock()
    request = MagicMock()
    setup_dishka_mock(request, db, audit)
    user = MagicMock()
    user.id = uuid.uuid4()

    enrollment = MagicMock()
    enrollment.id = uuid.uuid4()
    enrollment.user_id = user.id
    enrollment.label = "my-label"
    enrollment.is_active = False
    enrollment.confirmed_at = None
    db.get = AsyncMock(return_value=enrollment)

    from app.auth.schemas import TotpEnrollmentConfirmIn

    payload = TotpEnrollmentConfirmIn(enrollment_id=uuid.uuid4(), code="123456")

    with patch(
        "app.auth.mfa.complete_totp_enrollment",
        side_effect=HTTPException(400, "invalid_code"),
    ):
        with pytest.raises(HTTPException) as exc:
            await mfa_api.confirm_totp_enrollment(
                payload=payload, request=request, db=db, user=user
            )
        assert exc.value.status_code == 400
        audit.log.assert_called_once()


@pytest.mark.asyncio
async def test_mfa_start_totp_enrollment_endpoint():
    db = AsyncMock()
    audit = MagicMock()
    request = MagicMock()
    setup_dishka_mock(request, db, audit)
    user = MagicMock()
    user.id = uuid.uuid4()

    from app.auth.schemas import TotpEnrollmentStartIn

    payload = TotpEnrollmentStartIn(label="my-token", reuse_existing=True)

    enrollment = MagicMock()
    enrollment.id = uuid.uuid4()
    enrollment.user_id = user.id
    enrollment.label = "my-label"
    enrollment.is_active = False
    enrollment.confirmed_at = None
    enrollment.created_at = datetime.now(UTC)

    with (
        patch("app.models.user_loaders.ensure_mfa_relationships_loaded", AsyncMock()),
        patch(
            "app.auth.mfa.start_totp_enrollment",
            AsyncMock(return_value=(enrollment, "secret", "url")),
        ),
    ):
        res = await mfa_api.start_totp_enrollment_endpoint(
            request=request, db=db, payload=payload, user=user
        )
        assert res.secret == "secret"  # pragma: allowlist secret
        assert res.otpauth_url == "url"


# ----------------------------------------------------
# 2. app/api/notifications.py
# ----------------------------------------------------


def test_parse_datetime_timestamp_variants():
    # timestamp > 1e12
    assert notifications_api._parse_datetime(2000000000000) is not None
    # OSError / OverflowError on invalid timestamp
    assert notifications_api._parse_datetime(1e30) is None
    assert notifications_api._parse_datetime("invalid-date") is None


def test_localized_notification_field_required():
    assert (
        notifications_api._localized_notification_field("en", None, None, required=True)
        == ""
    )
    assert (
        notifications_api._localized_notification_field("en", "RU", None, required=True)
        == "RU"
    )
    assert (
        notifications_api._localized_notification_field("en", None, "EN", required=True)
        == "EN"
    )


@pytest.mark.asyncio
async def test_existing_notification_columns_mocked():
    db = AsyncMock()
    sync_session = MagicMock()
    sync_session.bind = None

    async def run_sync(fn):
        return fn(sync_session)

    db.run_sync = run_sync

    cols = await notifications_api._existing_notification_columns(db)
    assert cols == set()


@pytest.mark.asyncio
async def test_list_notifications_bad_cursor():
    request = MagicMock()
    db = AsyncMock()
    user = MagicMock()
    response = MagicMock()
    with pytest.raises(HTTPException) as exc:
        await notifications_api.list_notifications(
            request, response, db=db, user=user, cursor="invalid_base64_string"
        )
    assert exc.value.status_code == 400

    bad_cursor = base64.b64encode(b"2026-01-01T00:00:00,not-a-uuid").decode()
    with pytest.raises(HTTPException) as exc:
        await notifications_api.list_notifications(
            request, response, db=db, user=user, cursor=bad_cursor
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_fetch_notification_rows_fallback_empty():
    db = AsyncMock()
    with patch(
        "app.api.notifications._existing_notification_columns",
        AsyncMock(return_value=set()),
    ):
        res, cols = await notifications_api._fetch_notification_rows_fallback(
            db, "user-id", limit=10, cursor_info=None
        )
        assert res == []
        assert cols == set()


# ----------------------------------------------------
# 3. app/routers/notifications.py
# ----------------------------------------------------


@pytest.mark.asyncio
async def test_subscribe_integrity_error_retry():
    from app.schemas.notifications import PushSubscriptionIn

    payload = PushSubscriptionIn(
        endpoint="https://updates.push.services.mozilla.com/wpush/v2/gAAAAA",
        keys={"p256dh": "BEl62vOgw1...", "auth": "qQX4S..."},
        topics=["general"],
    )
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = MagicMock()
    request.headers.get.return_value = "Mozilla/5.0"

    with (
        patch("app.routers.notifications.enforce_rate_limit", AsyncMock()),
        patch("app.routers.notifications.resolve_locale", MagicMock(return_value="en")),
        patch(
            "app.routers.notifications.resolve_topics",
            MagicMock(return_value={"general"}),
        ),
    ):
        db = AsyncMock()
        db.add = MagicMock()
        nested_mock = MagicMock()
        nested_mock.__aenter__ = AsyncMock()
        nested_mock.__aexit__ = AsyncMock()
        db.begin_nested = MagicMock(return_value=nested_mock)

        user = MagicMock()
        user.id = uuid.uuid4()

        db.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        call_count = 0

        async def mock_flush():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise IntegrityError("statement", {}, Exception())

        db.flush = mock_flush

        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        async def mock_refresh(sub):
            sub.id = uuid.uuid4()

        db.refresh = mock_refresh

        with patch("asyncio.sleep", AsyncMock()):
            res = await push_router.subscribe(payload, request, db, user)
            assert res is not None
            assert call_count >= 2


@pytest.mark.asyncio
async def test_update_subscription_topics_not_found():
    from app.schemas.notifications import PushSubscriptionTopicsUpdate

    payload = PushSubscriptionTopicsUpdate(
        endpoint="https://some-endpoint", topics=["general"]
    )
    request = MagicMock()
    db = AsyncMock()
    user = MagicMock()
    user.id = uuid.uuid4()

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_res

    with pytest.raises(HTTPException) as exc:
        await push_router.update_subscription_topics(payload, request, db, user)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_unsubscribe_errors():
    from app.schemas.notifications import PushSubscriptionDelete

    request = MagicMock()
    request.client.host = "127.0.0.1"
    db = AsyncMock()
    user = MagicMock()
    user.id = uuid.uuid4()

    payload = PushSubscriptionDelete(endpoint="")
    with pytest.raises(HTTPException) as exc:
        await push_router.unsubscribe(payload, request, db, user)
    assert exc.value.status_code == 400

    from app.core.ratelimit import RateLimitExceeded, RateLimitInfo

    payload2 = PushSubscriptionDelete(endpoint="https://some-endpoint")
    info = RateLimitInfo(allowed=False, remaining=0, retry_after=5)
    with patch(
        "app.routers.notifications.enforce_rate_limit",
        side_effect=RateLimitExceeded(info),
    ):
        with pytest.raises(HTTPException) as exc:
            await push_router.unsubscribe(payload2, request, db, user)
        assert exc.value.status_code == 429


# ----------------------------------------------------
# 4. app/api/spotify.py
# ----------------------------------------------------


def test_spotify_mint_state_token_no_secret():
    with patch("app.api.spotify.settings") as mock_settings:
        mock_settings.spotify_oauth_state_secret = ""
        with pytest.raises(ValueError, match="SPOTIFY_OAUTH_STATE_SECRET must be set"):
            spotify_api._mint_state_token("user1", expires_minutes=5)


def test_spotify_coerce_expires():
    assert spotify_api._coerce_expires("invalid") == 3600
    assert spotify_api._coerce_expires(None) == 3600
    assert spotify_api._coerce_expires(10) == 30
    assert spotify_api._coerce_expires(60) == 60


def test_spotify_disconnect_user_none():
    mock_user = MagicMock()
    mock_user.spotify = None
    spotify_api._disconnect_user(mock_user)


def test_spotify_fallback_now_playing_none():
    mock_user = MagicMock()
    mock_user.spotify = None
    res = spotify_api._fallback_now_playing(mock_user)
    assert not res.is_playing


@pytest.mark.asyncio
async def test_now_playing_endpoint_error_states():
    db = AsyncMock()
    user = MagicMock()
    user.spotify = MagicMock()
    user.spotify.access_token = "access"
    user.spotify.last_track_id = "t1"
    user.spotify.last_track_name = "Track1"
    user.spotify.last_album_name = "Album1"
    user.spotify.last_album_image_url = "http://image"
    user.spotify.last_track_url = "http://track"
    user.spotify.last_artist_name = "Artist1"

    request = MagicMock()

    with (
        patch("app.api.spotify._ensure_access_token", AsyncMock(return_value="token")),
        patch(
            "app.api.spotify._spotify_http_client.get",
            AsyncMock(return_value=Response(204)),
        ),
    ):
        res = await spotify_api.now_playing(request=request, db=db, user=user)
        assert res.status_code == 204
        assert not user.spotify.is_playing

    with (
        patch("app.api.spotify._ensure_access_token", AsyncMock(return_value="token")),
        patch(
            "app.api.spotify._spotify_http_client.get",
            AsyncMock(return_value=Response(401)),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await spotify_api.now_playing(request=request, db=db, user=user)
        assert exc.value.status_code == 401
        assert not user.spotify.is_connected

    user.spotify.is_connected = True
    resp_429 = Response(429)
    resp_429.headers["Retry-After"] = "10"
    with (
        patch("app.api.spotify._ensure_access_token", AsyncMock(return_value="token")),
        patch(
            "app.api.spotify._spotify_http_client.get", AsyncMock(return_value=resp_429)
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await spotify_api.now_playing(request=request, db=db, user=user)
        assert exc.value.status_code == 429

    from app.core.circuit_breaker import CircuitBreakerOpenError

    with (
        patch("app.api.spotify._ensure_access_token", AsyncMock(return_value="token")),
        patch(
            "app.api.spotify._spotify_http_client.get",
            side_effect=CircuitBreakerOpenError(
                "open", remaining_seconds=10.0, failure_count=5
            ),
        ),
    ):
        res = await spotify_api.now_playing(request=request, db=db, user=user)
        assert not res.is_playing


# ----------------------------------------------------
# 5. app/core/metrics.py
# ----------------------------------------------------


def test_configure_metrics_placeholder_credentials():
    app = MagicMock()
    app.state = MagicMock()
    app.state._metrics_configured = False

    with patch("app.core.metrics.settings") as mock_settings:
        mock_settings.enable_metrics_endpoint = True
        mock_settings.metrics_basic_auth_password = "admin"  # pragma: allowlist secret
        mock_settings.metrics_basic_auth_username = "admin"

        metrics_core.configure_metrics(app)
        assert not getattr(app.state, "_metrics_configured", False)


@pytest.mark.asyncio
async def test_request_metrics_middleware_exception():
    app = MagicMock()

    async def call_next(req):
        raise ValueError("test-error")

    middleware = metrics_core.PrometheusRequestMetricsMiddleware(app)
    request = MagicMock()
    request.method = "GET"

    with patch("app.core.metrics._REQUEST_COUNT"):
        with pytest.raises(ValueError, match="test-error"):
            await middleware.dispatch(request, call_next)


def test_record_system_metrics_gputil():
    with patch("app.core.metrics._load_gputil") as mock_gputil:
        gpu = MagicMock()
        gpu.id = 0
        gpu.name = "Tesla V100"
        gpu.load = 0.5
        mock_gputil.return_value.getGPUs.return_value = [gpu]

        metrics_core._record_system_metrics()


# ----------------------------------------------------
# 6. app/core/observability.py
# ----------------------------------------------------


def test_observability_resolve_headers():
    res = observability_core._resolve_headers("a=1,,b=2")
    assert res == {"a": "1", "b": "2"}


def test_observability_resolve_current_trace_id_fallback():
    with patch("opentelemetry.trace.get_current_span") as mock_span:
        mock_span.return_value.get_span_context.return_value = None
        tid = observability_core._resolve_current_trace_id()
        assert tid is None


# ----------------------------------------------------
# 7. app/core/database.py
# ----------------------------------------------------


def test_database_adapt_datetime():
    dt = datetime(2026, 1, 1, 12, 0, 0)
    assert database_core.adapt_datetime(dt) == "2026-01-01T12:00:00"


def test_database_set_sqlite_pragma():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor

    with patch("app.core.database.isinstance", return_value=True):
        database_core.set_sqlite_pragma(conn, None)
        cursor.execute.assert_any_call("PRAGMA journal_mode=WAL")
        cursor.execute.assert_any_call("PRAGMA foreign_keys=ON")
        cursor.close.assert_called_once()


# ----------------------------------------------------
# 8. app/api/websocket.py
# ----------------------------------------------------


def test_websocket_audit_context():
    ws = MagicMock()
    ws.url.path = "/ws/chat"
    ws.client = None
    ctx = websocket_api._get_websocket_audit_context(ws)
    assert ctx["ws_path"] == "/ws/chat"
    assert ctx["ws_client"] is None


@pytest.mark.asyncio
async def test_websocket_chat_connect_rejected():
    ws = MagicMock()
    ws.headers = {}
    ws.query_params = {}
    ws.cookies = {}
    from app.models import User

    user = User(id=uuid.uuid4())
    session_jti = "some-session-jti"

    with (
        patch(
            "app.api.ws.authenticator.authenticator.authenticate_upgrade",
            AsyncMock(return_value=(user, session_jti, None)),
        ),
        patch("app.api.websocket.manager.connect", AsyncMock(return_value=False)),
    ):
        await websocket_api.websocket_chat(ws)


# ----------------------------------------------------
# 9. app/graphql/extensions.py
# ----------------------------------------------------


@pytest.mark.asyncio
async def test_increment_user_cost_redis_error():
    mock_redis = MagicMock()
    mock_redis.pipeline.side_effect = ConnectionError("redis-down")

    with patch("app.deps.cache.get_cache_client", AsyncMock(return_value=mock_redis)):
        cost1 = await graphql_extensions._increment_user_cost("user1", 10, 12345)
        assert cost1 == 10
        cost2 = await graphql_extensions._increment_user_cost("user1", 15, 12345)
        assert cost2 == 25

        cost3 = await graphql_extensions._increment_user_cost("user1", 5, 12346)
        assert cost3 == 5


# ----------------------------------------------------
# 10. app/api/users.py
# ----------------------------------------------------


def test_enforce_profile_cache_integrity_errors():
    with patch("app.api.users.settings") as mock_settings:
        mock_settings.environment = "production"

        # 1. Missing header
        req = MagicMock()
        req.headers = {}
        with pytest.raises(HTTPException) as exc:
            users_api._enforce_profile_cache_integrity(req)
        assert exc.value.status_code == 400

        # 2. Too large header
        req2 = MagicMock()
        req2.headers = {"x-profile-cache-envelope": "a" * 10000}
        with pytest.raises(HTTPException) as exc:
            users_api._enforce_profile_cache_integrity(req2)
        assert exc.value.status_code == 400

        # 3. Invalid json
        req3 = MagicMock()
        req3.headers = {"x-profile-cache-envelope": "invalid_json"}
        with pytest.raises(HTTPException) as exc:
            users_api._enforce_profile_cache_integrity(req3)
        assert exc.value.status_code == 400

        # 4. Valid payload structure but invalid signature
        envelope = {
            "version": 1,
            "expiresAt": int(
                (datetime.now(UTC) + timedelta(minutes=5)).timestamp() * 1000
            ),
            "data": "some_data",
            "signature": "bad_sig",
        }
        req4 = MagicMock()
        req4.headers = {"x-profile-cache-envelope": json.dumps(envelope)}
        req4.state.active_session = MagicMock()
        req4.state.active_session.signing_key = "secret"
        with pytest.raises(HTTPException) as exc:
            users_api._enforce_profile_cache_integrity(req4)
        assert exc.value.status_code == 400

        # 5. Invalid expiresAt type / expired
        envelope["expiresAt"] = "not-a-date-or-number"
        payload_for_sig = {
            "version": envelope["version"],
            "expiresAt": envelope["expiresAt"],
            "data": envelope["data"],
        }
        payload_json = json.dumps(payload_for_sig, separators=(",", ":"))
        digest = hmac.new(b"secret", payload_json.encode(), hashlib.sha256).digest()
        envelope["signature"] = base64.b64encode(digest).decode("ascii")

        req5 = MagicMock()
        req5.headers = {"x-profile-cache-envelope": json.dumps(envelope)}
        req5.state.active_session = MagicMock()
        req5.state.active_session.signing_key = "secret"
        with pytest.raises(HTTPException) as exc:
            users_api._enforce_profile_cache_integrity(req5)
        assert exc.value.status_code == 400
