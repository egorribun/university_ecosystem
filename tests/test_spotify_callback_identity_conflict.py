from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ConnectError, Response
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from app.api import spotify as spotify_api
from app.core.circuit_breaker import CircuitBreakerOpenError
from app.models import SpotifyIntegration, User
from tests.conftest import call_injected


class _CallbackCircuitBreaker:
    def __init__(self, *, opens_on_entry: int | None = None) -> None:
        self.opens_on_entry = opens_on_entry
        self.entries = 0

    async def __aenter__(self) -> _CallbackCircuitBreaker:
        self.entries += 1
        if self.entries == self.opens_on_entry:
            raise CircuitBreakerOpenError(
                "spotify", remaining_seconds=5, failure_count=3
            )
        return self

    async def __aexit__(self, *_exc_info: object) -> bool:
        return False


def _callback_request() -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/spotify/callback",
            "headers": [(b"accept-language", b"en")],
            "query_string": b"",
        }
    )
    request.state.active_session = SimpleNamespace(id=uuid4())
    return request


def _install_callback_mocks(monkeypatch: pytest.MonkeyPatch, *, attempts: int = 1):
    monkeypatch.setattr(
        spotify_api,
        "settings",
        SimpleNamespace(
            frontend_origin="https://frontend.example.test",
            spotify_client_id="synthetic-client",
            spotify_client_secret="",
            spotify_redirect_uri="https://api.example.test/spotify/callback",
        ),
    )
    monkeypatch.setattr(spotify_api, "_consume_oauth_state", AsyncMock())
    monkeypatch.setattr(
        spotify_api, "_spotify_circuit_breaker", _CallbackCircuitBreaker()
    )
    post = AsyncMock(
        side_effect=[
            Response(
                200,
                json={
                    "access_token": f"synthetic-access-{index}",
                    "refresh_token": f"synthetic-refresh-{index}",
                    "expires_in": 3600,
                    "scope": "user-read-currently-playing",
                },
            )
            for index in range(attempts)
        ]
    )
    get = AsyncMock()
    monkeypatch.setattr(
        spotify_api, "_spotify_http_client", SimpleNamespace(post=post, get=get)
    )
    return post, get


async def _run_callback(db, user: User | SimpleNamespace):
    return await call_injected(
        spotify_api.spotify_callback,
        _callback_request(),
        user=user,
        code="synthetic-code",
        state="synthetic-state",
        provides={"AsyncDatabaseSession": db},
    )


@pytest.mark.asyncio
async def test_spotify_id_conflict_rolls_back_existing_requester_tokens(
    db_session, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await user_factory()
    requester = await user_factory()
    owner_id = owner.id
    requester_id = requester.id
    owner.spotify.spotify_user_id = "spotify-account-owned-fixture"
    owner.spotify.display_name = "Current owner"
    requester.spotify.spotify_user_id = None
    requester.spotify.access_token = "prior-access-fixture"
    requester.spotify.refresh_token = "prior-refresh-fixture"
    requester.spotify.scope = "prior-scope"
    requester.spotify.is_connected = False
    await db_session.commit()

    _post, get = _install_callback_mocks(monkeypatch)
    get.return_value = Response(
        200,
        json={
            "id": "spotify-account-owned-fixture",
            "display_name": "Conflicting profile",
        },
    )

    response = await _run_callback(db_session, requester)

    assert response.status_code == 302
    assert response.headers["location"] == (
        "https://frontend.example.test/profile?spotify=error"
    )
    persisted_owner = await db_session.get(
        SpotifyIntegration, owner_id, populate_existing=True
    )
    persisted_requester = await db_session.get(
        SpotifyIntegration, requester_id, populate_existing=True
    )
    assert persisted_owner is not None
    assert persisted_owner.spotify_user_id == "spotify-account-owned-fixture"
    assert persisted_owner.display_name == "Current owner"
    assert persisted_requester is not None
    assert persisted_requester.spotify_user_id is None
    assert persisted_requester.access_token == "prior-access-fixture"
    assert persisted_requester.refresh_token == "prior-refresh-fixture"
    assert persisted_requester.scope == "prior-scope"
    assert persisted_requester.is_connected is False


@pytest.mark.asyncio
async def test_spotify_id_conflict_does_not_create_requester_integration(
    db_session, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await user_factory()
    owner_id = owner.id
    owner.spotify.spotify_user_id = "spotify-account-owned-fixture"
    await db_session.commit()

    requester = User(
        email=f"requester-{uuid4().hex}@example.com",
        hashed_password=uuid4().hex,
        role="student",
        _allow_system_managed_assignment=True,
    )
    db_session.add(requester)
    await db_session.commit()
    requester_id = requester.id

    _post, get = _install_callback_mocks(monkeypatch)
    get.return_value = Response(
        200,
        json={
            "id": "spotify-account-owned-fixture",
            "display_name": "Conflicting profile",
        },
    )

    response = await _run_callback(db_session, requester)

    assert response.status_code == 302
    assert response.headers["location"].endswith("/profile?spotify=error")
    persisted_owner = await db_session.get(
        SpotifyIntegration, owner_id, populate_existing=True
    )
    persisted_requester = await db_session.get(
        SpotifyIntegration, requester_id, populate_existing=True
    )
    assert persisted_owner is not None
    assert persisted_owner.spotify_user_id == "spotify-account-owned-fixture"
    assert persisted_requester is None


@pytest.mark.asyncio
async def test_spotify_same_account_relink_retry_is_idempotent(
    db_session, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await user_factory()
    user_id = user.id
    user.spotify.spotify_user_id = "spotify-account-owned-fixture"
    user.spotify.access_token = "prior-access-fixture"
    await db_session.commit()

    _post, get = _install_callback_mocks(monkeypatch, attempts=2)
    get.side_effect = [
        Response(
            200,
            json={
                "id": "spotify-account-owned-fixture",
                "display_name": "First display name",
            },
        ),
        Response(
            200,
            json={
                "id": "spotify-account-owned-fixture",
                "display_name": "Latest display name",
            },
        ),
    ]

    first = await _run_callback(db_session, user)
    second = await _run_callback(db_session, user)

    assert first.status_code == 302
    assert first.headers["location"].endswith("/profile?spotify=connected")
    assert second.status_code == 302
    assert second.headers["location"].endswith("/profile?spotify=connected")
    persisted = await db_session.get(
        SpotifyIntegration, user_id, populate_existing=True
    )
    assert persisted is not None
    assert persisted.spotify_user_id == "spotify-account-owned-fixture"
    assert persisted.display_name == "Latest display name"
    assert persisted.access_token == "synthetic-access-1"
    assert persisted.refresh_token == "synthetic-refresh-1"


@pytest.mark.asyncio
async def test_unrelated_integrity_error_is_rolled_back_and_re_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        spotify=SimpleNamespace(
            access_token=None,
            refresh_token=None,
            token_expires_at=None,
            scope=None,
            is_connected=False,
            spotify_user_id="spotify-account-owned-fixture",
            display_name="Current display name",
        ),
    )
    db = AsyncMock()
    failure = IntegrityError(
        "synthetic unrelated constraint", {}, RuntimeError("constraint fixture")
    )
    db.commit.side_effect = failure
    db.scalar.return_value = user_id
    _post, get = _install_callback_mocks(monkeypatch)
    get.return_value = Response(
        200,
        json={
            "id": "spotify-account-owned-fixture",
            "display_name": "Updated display name",
        },
    )

    with pytest.raises(IntegrityError) as error:
        await _run_callback(db, user)

    assert error.value is failure
    db.rollback.assert_awaited_once()
    db.scalar.assert_awaited_once()


@pytest.mark.parametrize("profile_case", ["circuit-open", "non-200"])
@pytest.mark.asyncio
async def test_profile_unavailable_commits_tokens_without_identity(
    profile_case: str,
    db_session,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await user_factory()
    user_id = user.id
    _post, get = _install_callback_mocks(monkeypatch)
    if profile_case == "circuit-open":
        monkeypatch.setattr(
            spotify_api,
            "_spotify_circuit_breaker",
            _CallbackCircuitBreaker(opens_on_entry=2),
        )
    else:
        get.return_value = Response(503)

    response = await _run_callback(db_session, user)

    assert response.status_code == 302
    assert response.headers["location"].endswith("/profile?spotify=connected")
    if profile_case == "circuit-open":
        get.assert_not_awaited()
    else:
        get.assert_awaited_once()
    persisted = await db_session.get(
        SpotifyIntegration, user_id, populate_existing=True
    )
    assert persisted is not None
    assert persisted.access_token == "synthetic-access-0"
    assert persisted.refresh_token == "synthetic-refresh-0"
    assert persisted.spotify_user_id is None
    assert persisted.display_name is None


@pytest.mark.parametrize("failure_kind", ["transport", "json"])
@pytest.mark.asyncio
async def test_profile_lookup_failure_commits_tokens_then_reraises_original(
    failure_kind: str,
    db_session,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user = await user_factory()
    user_id = user.id
    _post, get = _install_callback_mocks(monkeypatch)
    if failure_kind == "transport":
        failure = ConnectError("synthetic profile transport failure")
        get.side_effect = failure
        expected_error = ConnectError
    else:
        get.return_value = Response(200, content=b"invalid-json-fixture")
        failure = None
        expected_error = json.JSONDecodeError

    with pytest.raises(expected_error) as raised:
        await _run_callback(db_session, user)

    if failure is not None:
        assert raised.value is failure
    persisted = await db_session.get(
        SpotifyIntegration, user_id, populate_existing=True
    )
    assert persisted is not None
    assert persisted.access_token == "synthetic-access-0"
    assert persisted.refresh_token == "synthetic-refresh-0"
    assert persisted.spotify_user_id is None
    assert all(
        "synthetic-access-0" not in record.getMessage()
        and "synthetic-refresh-0" not in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_profile_lookup_cancellation_commits_tokens_and_propagates(
    db_session,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user = await user_factory()
    user_id = user.id
    _post, get = _install_callback_mocks(monkeypatch)
    cancellation = asyncio.CancelledError("synthetic profile cancellation")
    get.side_effect = cancellation

    with pytest.raises(asyncio.CancelledError) as raised:
        await _run_callback(db_session, user)

    assert raised.value is cancellation
    persisted = await db_session.get(
        SpotifyIntegration, user_id, populate_existing=True
    )
    assert persisted is not None
    assert persisted.access_token == "synthetic-access-0"
    assert persisted.refresh_token == "synthetic-refresh-0"
    assert all(
        "synthetic-access-0" not in record.getMessage()
        and "synthetic-refresh-0" not in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.parametrize("profile_case", ["circuit-open", "non-200", "missing-id"])
@pytest.mark.asyncio
async def test_integrity_error_without_profile_identity_skips_owner_lookup(
    profile_case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        spotify=SimpleNamespace(
            access_token="prior-access-fixture",
            refresh_token="prior-refresh-fixture",
            token_expires_at=None,
            scope="prior-scope",
            is_connected=True,
            spotify_user_id="existing-profile-fixture",
            display_name="Existing profile",
        ),
    )
    db = AsyncMock()
    failure = IntegrityError(
        "synthetic unrelated constraint", {}, RuntimeError("constraint fixture")
    )
    db.commit.side_effect = failure
    _post, get = _install_callback_mocks(monkeypatch)
    if profile_case == "circuit-open":
        monkeypatch.setattr(
            spotify_api,
            "_spotify_circuit_breaker",
            _CallbackCircuitBreaker(opens_on_entry=2),
        )
    elif profile_case == "non-200":
        get.return_value = Response(503)
    else:
        get.return_value = Response(200, json={"display_name": "No ID fixture"})

    with pytest.raises(IntegrityError) as raised:
        await _run_callback(db, user)

    assert raised.value is failure
    db.rollback.assert_awaited_once()
    db.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_integrity_error_with_unowned_profile_id_is_reraised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        spotify=SimpleNamespace(
            access_token=None,
            refresh_token=None,
            token_expires_at=None,
            scope=None,
            is_connected=False,
            spotify_user_id=None,
            display_name=None,
        ),
    )
    db = AsyncMock()
    failure = IntegrityError(
        "synthetic unrelated constraint", {}, RuntimeError("constraint fixture")
    )
    db.commit.side_effect = failure
    db.scalar.return_value = None
    _post, get = _install_callback_mocks(monkeypatch)
    get.return_value = Response(
        200,
        json={
            "id": "spotify-account-unowned-fixture",
            "display_name": "Unowned profile fixture",
        },
    )

    with pytest.raises(IntegrityError) as raised:
        await _run_callback(db, user)

    assert raised.value is failure
    db.rollback.assert_awaited_once()
    db.scalar.assert_awaited_once()
    owner_query = db.scalar.await_args.args[0]
    compiled_query = owner_query.compile(compile_kwargs={"literal_binds": True})
    assert "spotify-account-unowned-fixture" in str(compiled_query)


@pytest.mark.asyncio
async def test_save_tokens_default_commit_and_explicit_staging_opt_out() -> None:
    user = SimpleNamespace(
        id=uuid4(),
        spotify=SimpleNamespace(
            access_token=None,
            refresh_token="prior-refresh-fixture",
            token_expires_at=None,
            scope=None,
            is_connected=False,
        ),
    )
    db = AsyncMock()

    await spotify_api._save_tokens(
        db, user, "synthetic-access-0", None, "scope-fixture", 3600
    )

    db.commit.assert_awaited_once()
    assert user.spotify.refresh_token == "prior-refresh-fixture"
    db.reset_mock()

    await spotify_api._save_tokens(
        db,
        user,
        "synthetic-access-1",
        None,
        "scope-fixture",
        3600,
        commit=False,
    )

    db.commit.assert_not_awaited()
