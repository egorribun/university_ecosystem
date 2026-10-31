"""Session changes after upgrade must gate both WebSocket directions."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketDisconnect

from app.api import websocket as websocket_api
from app.api.ws import auth
from app.api.ws.connection_manager import ConnectionManager


@pytest.fixture
def live_session(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    user = SimpleNamespace(id=uuid.uuid4(), is_active=True, mfa_epoch=0)
    session = SimpleNamespace(
        user_id=user.id,
        revoked_at=None,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        mfa_epoch=0,
    )
    redis = SimpleNamespace(exists=AsyncMock(return_value=0))
    session_repo = SimpleNamespace(get_by_jti=AsyncMock(return_value=session))

    @asynccontextmanager
    async def open_session() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(auth, "async_session", open_session)
    monkeypatch.setattr(
        auth, "get_revocation_redis_client", AsyncMock(return_value=redis)
    )
    monkeypatch.setattr(
        auth,
        "UserRepository",
        lambda _session: SimpleNamespace(get=AsyncMock(return_value=user)),
    )
    monkeypatch.setattr(
        auth,
        "SessionRepository",
        lambda _session: session_repo,
    )
    return SimpleNamespace(
        user=user, session=session, redis=redis, session_repo=session_repo
    )


def _invalidate(state: SimpleNamespace, reason: str) -> None:
    if reason == "tombstone":
        state.redis.exists.return_value = 1
    elif reason == "revoked":
        state.session.revoked_at = datetime.now(UTC)
    elif reason == "expired":
        state.session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif reason == "inactive":
        state.user.is_active = False
    elif reason == "mfa_epoch":
        state.user.mfa_epoch = 1
    elif reason == "revocation_unavailable":
        state.redis.exists.side_effect = OSError("revocation store unavailable")
    elif reason == "database_unavailable":
        state.session_repo.get_by_jti.side_effect = OSError("session store unavailable")


@pytest.mark.asyncio
async def test_manager_rejects_registration_without_a_session() -> None:
    manager = ConnectionManager()
    websocket = AsyncMock()
    user_id = uuid.uuid4()

    assert not await manager.connect(websocket, user_id, session_jti="")
    websocket.accept.assert_not_awaited()
    websocket.close.assert_awaited_once_with(
        code=4001, reason="Authentication required"
    )
    assert not manager.is_online(user_id)


@pytest.mark.asyncio
async def test_upgrade_without_session_does_not_register(
    monkeypatch: pytest.MonkeyPatch, live_session: SimpleNamespace
) -> None:
    websocket = AsyncMock()
    manager = ConnectionManager()
    monkeypatch.setattr(websocket_api, "manager", manager)
    monkeypatch.setattr(
        "app.api.ws.authenticator.authenticator.authenticate_upgrade",
        AsyncMock(return_value=(live_session.user, None, None)),
    )

    await websocket_api.websocket_chat(websocket)

    websocket.close.assert_awaited_once_with(
        code=4001, reason="Authentication required"
    )
    websocket.accept.assert_not_awaited()
    assert not manager.is_online(live_session.user.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("close_fails", [False, True])
async def test_missing_session_mapping_cannot_receive_and_is_removed(
    close_fails: bool,
) -> None:
    manager = ConnectionManager()
    websocket = AsyncMock()
    user_id = uuid.uuid4()
    manager.active_connections[user_id] = {websocket}
    manager.connection_users[websocket] = user_id
    if close_fails:
        websocket.close.side_effect = RuntimeError("socket already closed")

    assert await manager.send_to_user(user_id, {"type": "message"}) == 0
    websocket.send_json.assert_not_awaited()
    websocket.close.assert_awaited_once_with(
        code=4001, reason="Session expired or revoked"
    )
    assert not manager.is_online(user_id)


@pytest.mark.asyncio
async def test_rate_limited_frames_do_not_trigger_per_frame_session_queries(
    monkeypatch: pytest.MonkeyPatch, live_session: SimpleNamespace
) -> None:
    websocket = AsyncMock()
    websocket.app = SimpleNamespace(state=SimpleNamespace())
    websocket.receive_text.side_effect = ["{}", "{}", WebSocketDisconnect(code=1000)]
    manager = ConnectionManager()
    manager.broadcast_presence = AsyncMock(return_value=0)
    monkeypatch.setattr(manager, "check_rate_limit", lambda _websocket: False)
    monkeypatch.setattr(websocket_api, "manager", manager)
    monkeypatch.setattr(
        websocket_api, "_update_last_seen", AsyncMock(return_value=datetime.now(UTC))
    )
    monkeypatch.setattr(
        "app.api.ws.authenticator.authenticator.authenticate_upgrade",
        AsyncMock(return_value=(live_session.user, "session", None)),
    )

    await websocket_api.websocket_chat(websocket)

    live_session.redis.exists.assert_not_awaited()
    assert websocket.send_json.await_count == 2
    assert not manager.is_online(live_session.user.id)


@pytest.mark.asyncio
async def test_continuously_rate_limited_socket_still_revalidates_on_deadline(
    monkeypatch: pytest.MonkeyPatch, live_session: SimpleNamespace
) -> None:
    websocket = AsyncMock()
    websocket.app = SimpleNamespace(state=SimpleNamespace())
    reads = 0

    async def receive_text() -> str:
        nonlocal reads
        reads += 1
        if reads == 2:
            _invalidate(live_session, "tombstone")
        return "{}"

    websocket.receive_text.side_effect = receive_text
    manager = ConnectionManager()
    manager.broadcast_presence = AsyncMock(return_value=0)
    monkeypatch.setattr(manager, "check_rate_limit", lambda _websocket: False)
    monkeypatch.setattr(websocket_api, "manager", manager)
    monkeypatch.setattr(websocket_api, "_WS_SESSION_REVALIDATION_SECONDS", 0.01)
    monkeypatch.setattr(
        websocket_api, "_update_last_seen", AsyncMock(return_value=datetime.now(UTC))
    )
    monkeypatch.setattr(
        "app.api.ws.authenticator.authenticator.authenticate_upgrade",
        AsyncMock(return_value=(live_session.user, "session", None)),
    )

    await asyncio.wait_for(websocket_api.websocket_chat(websocket), timeout=2)

    assert reads == 2
    live_session.redis.exists.assert_awaited_once()
    websocket.close.assert_awaited_once_with(
        code=4001, reason="Session expired or revoked"
    )
    assert not manager.is_online(live_session.user.id)


@pytest.mark.parametrize(
    "reason",
    [
        "tombstone",
        "revoked",
        "expired",
        "inactive",
        "mfa_epoch",
        "revocation_unavailable",
        "database_unavailable",
    ],
)
@pytest.mark.asyncio
async def test_changed_session_cannot_dispatch_after_upgrade(
    monkeypatch: pytest.MonkeyPatch, live_session: SimpleNamespace, reason: str
) -> None:
    websocket = AsyncMock()
    websocket.app = SimpleNamespace(state=SimpleNamespace())
    manager = ConnectionManager()
    manager.broadcast_presence = AsyncMock(return_value=0)
    dispatcher = SimpleNamespace(dispatch=AsyncMock())
    first_read = True

    async def receive_text() -> str:
        nonlocal first_read
        if first_read:
            first_read = False
            _invalidate(live_session, reason)
            return '{"type":"get_online"}'
        raise WebSocketDisconnect(code=1000)

    websocket.receive_text.side_effect = receive_text
    monkeypatch.setattr(websocket_api, "manager", manager)
    monkeypatch.setattr(
        websocket_api, "_update_last_seen", AsyncMock(return_value=datetime.now(UTC))
    )
    monkeypatch.setattr(
        "app.api.ws.authenticator.authenticator.authenticate_upgrade",
        AsyncMock(return_value=(live_session.user, "session", None)),
    )
    monkeypatch.setattr(
        "app.api.ws.dispatcher.MessageDispatcher", lambda *_a, **_k: dispatcher
    )

    await websocket_api.websocket_chat(websocket)

    dispatcher.dispatch.assert_not_awaited()
    websocket.close.assert_awaited_once_with(
        code=4001, reason="Session expired or revoked"
    )
    assert not manager.is_online(live_session.user.id)


@pytest.mark.parametrize(
    "reason", ["tombstone", "expired", "revocation_unavailable", "database_unavailable"]
)
@pytest.mark.asyncio
async def test_changed_session_cannot_receive_outbound_frame(
    monkeypatch: pytest.MonkeyPatch, live_session: SimpleNamespace, reason: str
) -> None:
    websocket = AsyncMock()
    websocket.app = SimpleNamespace(state=SimpleNamespace())
    registered = asyncio.Event()
    release = asyncio.Event()

    async def receive_text() -> str:
        registered.set()
        await release.wait()
        raise WebSocketDisconnect(code=1000)

    websocket.receive_text.side_effect = receive_text
    manager = ConnectionManager()
    manager.broadcast_presence = AsyncMock(return_value=0)
    monkeypatch.setattr(websocket_api, "manager", manager)
    monkeypatch.setattr(
        websocket_api, "_update_last_seen", AsyncMock(return_value=datetime.now(UTC))
    )
    monkeypatch.setattr(
        "app.api.ws.authenticator.authenticator.authenticate_upgrade",
        AsyncMock(return_value=(live_session.user, "session", None)),
    )

    task = asyncio.create_task(websocket_api.websocket_chat(websocket))
    try:
        await asyncio.wait_for(registered.wait(), timeout=2)
        assert await manager.send_to_user(live_session.user.id, {"type": "before"}) == 1
        websocket.send_json.reset_mock()
        _invalidate(live_session, reason)
        assert await manager.send_to_user(live_session.user.id, {"type": "after"}) == 0
        websocket.send_json.assert_not_awaited()
        websocket.close.assert_awaited_once_with(
            code=4001, reason="Session expired or revoked"
        )
    finally:
        release.set()
        await asyncio.wait_for(task, timeout=2)

    assert not manager.is_online(live_session.user.id)


@pytest.mark.asyncio
async def test_revoked_tab_does_not_disable_another_session_of_the_same_user(
    live_session: SimpleNamespace,
) -> None:
    manager = ConnectionManager()
    revoked, active = AsyncMock(), AsyncMock()
    await manager.connect(revoked, live_session.user.id, session_jti="revoked")
    await manager.connect(active, live_session.user.id, session_jti="active")
    live_session.redis.exists.side_effect = lambda key: key.endswith(":revoked")

    sent = await manager.send_to_user(live_session.user.id, {"type": "message"})

    assert sent == 1
    revoked.send_json.assert_not_awaited()
    revoked.close.assert_awaited_once_with(
        code=4001, reason="Session expired or revoked"
    )
    active.send_json.assert_awaited_once_with({"type": "message"})
    assert manager.connection_sessions == {active: "active"}
    assert manager.is_online(live_session.user.id)
    await manager.disconnect(active)


@pytest.mark.asyncio
async def test_idle_connection_closes_after_session_is_revoked(
    monkeypatch: pytest.MonkeyPatch, live_session: SimpleNamespace
) -> None:
    websocket = AsyncMock()
    websocket.app = SimpleNamespace(state=SimpleNamespace())
    waiting_for_frame = asyncio.Event()

    async def receive_text() -> str:
        waiting_for_frame.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    websocket.receive_text.side_effect = receive_text
    manager = ConnectionManager()
    manager.broadcast_presence = AsyncMock(return_value=0)
    monkeypatch.setattr(websocket_api, "manager", manager)
    monkeypatch.setattr(
        websocket_api, "_WS_SESSION_REVALIDATION_SECONDS", 0.01, raising=False
    )
    monkeypatch.setattr(
        websocket_api, "_update_last_seen", AsyncMock(return_value=datetime.now(UTC))
    )
    monkeypatch.setattr(
        "app.api.ws.authenticator.authenticator.authenticate_upgrade",
        AsyncMock(return_value=(live_session.user, "session", None)),
    )

    task = asyncio.create_task(websocket_api.websocket_chat(websocket))
    try:
        await asyncio.wait_for(waiting_for_frame.wait(), timeout=2)
        _invalidate(live_session, "tombstone")
        done, _pending = await asyncio.wait({task}, timeout=0.5)
        assert task in done
        await task
        websocket.close.assert_awaited_once_with(
            code=4001, reason="Session expired or revoked"
        )
        assert not manager.is_online(live_session.user.id)
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


@pytest.mark.asyncio
async def test_idle_revalidation_preserves_a_valid_pending_receive(
    monkeypatch: pytest.MonkeyPatch, live_session: SimpleNamespace
) -> None:
    websocket = AsyncMock()
    websocket.app = SimpleNamespace(state=SimpleNamespace())
    release, checked = asyncio.Event(), asyncio.Event()
    reads = 0

    async def receive_text() -> str:
        nonlocal reads
        reads += 1
        if reads == 1:
            await release.wait()
            return '{"type":"get_online"}'
        raise WebSocketDisconnect(code=1000)

    async def revocation_check(_key: str) -> int:
        checked.set()
        return 0

    live_session.redis.exists.side_effect = revocation_check
    websocket.receive_text.side_effect = receive_text
    manager = ConnectionManager()
    manager.broadcast_presence = AsyncMock(return_value=0)
    dispatcher = SimpleNamespace(dispatch=AsyncMock())
    monkeypatch.setattr(websocket_api, "manager", manager)
    monkeypatch.setattr(websocket_api, "_WS_SESSION_REVALIDATION_SECONDS", 0.01)
    monkeypatch.setattr(
        websocket_api, "_update_last_seen", AsyncMock(return_value=datetime.now(UTC))
    )
    monkeypatch.setattr(
        "app.api.ws.authenticator.authenticator.authenticate_upgrade",
        AsyncMock(return_value=(live_session.user, "session", None)),
    )
    monkeypatch.setattr(
        "app.api.ws.dispatcher.MessageDispatcher", lambda *_a, **_k: dispatcher
    )

    task = asyncio.create_task(websocket_api.websocket_chat(websocket))
    try:
        await asyncio.wait_for(checked.wait(), timeout=2)
        assert reads == 1
        release.set()
        await asyncio.wait_for(task, timeout=2)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    dispatcher.dispatch.assert_awaited_once_with(
        websocket, live_session.user, "session", {"type": "get_online"}
    )
    websocket.close.assert_not_awaited()
    assert not manager.connection_sessions
