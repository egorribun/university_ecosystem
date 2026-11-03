"""Protocol lifecycle controls with mocked TLS; not a cryptographic proof."""

from __future__ import annotations

import asyncio
import ssl
from datetime import timedelta
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives.serialization import Encoding
from uvicorn.config import Config
from uvicorn.server import ServerState

from app.server import spiffe_transport as transport_module
from app.server.spiffe_identity import (
    TLSGeneration,
    WorkloadContexts,
    WorkloadIdentityError,
)
from app.server.spiffe_transport import TransportGuard, guarded_protocols
from tests.test_spiffe_identity import IDENTITY, NOW, leaf


class Transport(asyncio.Transport):
    def __init__(self, tls: object) -> None:
        self.tls = tls
        self.aborted = False

    def get_extra_info(self, name: str, default: object = None) -> object:
        return self.tls if name == "ssl_object" else default

    def abort(self) -> None:
        self.aborted = True

    def close(self) -> None:
        self.aborted = True

    def is_closing(self) -> bool:
        return self.aborted


@pytest.fixture
def setup_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TransportGuard, Mock, Mock, Transport]:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.verify_mode = ssl.CERT_REQUIRED
    generation = TLSGeneration(context, b"first", NOW + timedelta(minutes=1))
    source = Mock(spec=WorkloadContexts)
    source.current.return_value = generation
    loop = Mock(spec=asyncio.AbstractEventLoop)
    guard = TransportGuard(source, frozenset({IDENTITY}), loop)
    clock = Mock()
    clock.now.return_value = NOW
    monkeypatch.setattr(transport_module, "datetime", clock)
    tls = Mock(spec=ssl.SSLObject)
    tls.context = context
    tls.session_reused = False
    tls.getpeercert.return_value = leaf((IDENTITY,)).public_bytes(Encoding.DER)
    tls.get_verified_chain.return_value = [tls.getpeercert.return_value]
    return guard, source, loop, Transport(tls)


def test_admits_actual_peer_then_tracks_expiry(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport],
) -> None:
    guard, source, loop, transport = setup_guard
    assert guard.start() is source.current.return_value.context
    assert guard.admit(transport)
    assert guard.valid(transport)
    assert transport in guard.connections
    assert loop.call_later.call_args.args[0] == 60
    assert not transport.aborted


@pytest.mark.parametrize(
    "failure",
    [
        "plaintext",
        "resumed",
        "wrong_context",
        "no_cert",
        "wrong_id",
        "bad_der",
        "unverified",
    ],
)
def test_rejects_before_protocol_dispatch(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport], failure: str
) -> None:
    guard, _source, _loop, transport = setup_guard
    tls = transport.tls
    if failure == "plaintext":
        transport.tls = None
    elif failure == "resumed":
        tls.session_reused = True
    elif failure == "wrong_context":
        tls.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    elif failure == "no_cert":
        tls.getpeercert.return_value = None
    elif failure == "wrong_id":
        tls.getpeercert.return_value = leaf((IDENTITY + "/other",)).public_bytes(
            Encoding.DER
        )
    elif failure == "bad_der":
        tls.getpeercert.return_value = b"invalid DER"
    else:
        tls.context.verify_mode = ssl.CERT_NONE
    assert not guard.admit(transport)
    assert transport.aborted
    assert not guard.connections


def test_rotation_aborts_existing_transport_even_after_ws_upgrade(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport],
) -> None:
    guard, source, _loop, transport = setup_guard
    assert guard.admit(transport)
    # WS upgrade readmits the same transport, independently of H11's registry.
    assert guard.admit(transport)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.verify_mode = ssl.CERT_REQUIRED
    source.current.return_value = TLSGeneration(
        context, b"rotated", NOW + timedelta(minutes=2)
    )
    guard.refresh()
    assert transport.aborted
    assert not guard.connections


def test_source_failure_closes_existing_and_rejects_new(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport],
) -> None:
    guard, source, _loop, transport = setup_guard
    assert guard.admit(transport)
    source.current.side_effect = WorkloadIdentityError("closed")
    guard.refresh()
    assert transport.aborted
    assert not guard.admit(Transport(transport.tls))


def test_current_check_cannot_use_stale_generation(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport],
) -> None:
    guard, source, _loop, transport = setup_guard
    assert guard.admit(transport)
    source.current.side_effect = WorkloadIdentityError("expired")
    assert not guard.valid(transport)
    assert transport.aborted


def test_close_detaches_callback_cancels_timer_and_transports(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport],
) -> None:
    guard, source, loop, transport = setup_guard
    guard.start()
    assert guard.admit(transport)
    guard.close()
    source.unsubscribe.assert_called_once()
    loop.call_later.return_value.cancel.assert_called()
    assert transport.aborted
    assert not guard.admit(Transport(transport.tls))


@pytest.mark.parametrize("servername", [None, "irrelevant.invalid"])
def test_client_hello_uses_source_not_sni(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport], servername: str | None
) -> None:
    guard, source, _loop, transport = setup_guard
    initial = guard.start()
    callback = initial.sni_callback
    assert callback is not None
    assert callback(transport.tls, servername, initial) is None
    assert transport.tls.context is source.current.return_value.context
    source.current.side_effect = WorkloadIdentityError("closed")
    assert (
        callback(transport.tls, servername, initial)
        == ssl.ALERT_DESCRIPTION_ACCESS_DENIED
    )


@pytest.mark.asyncio
async def test_http_buffered_events_and_ws_data_stay_guarded() -> None:
    guard = Mock(spec=TransportGuard)
    guard.admit.return_value = True
    guard.valid.return_value = False
    http, ws = guarded_protocols(guard)
    app_called = False

    async def app(scope: object, receive: object, send: object) -> None:
        nonlocal app_called
        app_called = True

    config = Config(app=app, lifespan="off", log_config=None)
    config.load()
    for protocol_class in (http, ws):
        protocol = protocol_class(config, ServerState(), {})
        transport = Transport(None)
        protocol.connection_made(transport)
        protocol.data_received(b"GET / HTTP/1.1\r\nHost: ignored\r\n\r\n")
        protocol.handle_events()
        assert not app_called
        assert guard.valid.call_count >= 2
        protocol.connection_lost(None)
        guard.remove.assert_called_with(transport)


def test_unexpected_refresh_failure_retires_authority_and_keeps_monitoring(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport],
) -> None:
    guard, source, loop, transport = setup_guard
    assert guard.admit(transport)
    source.current.side_effect = RuntimeError("unexpected adapter failure")
    with pytest.raises(RuntimeError, match="unexpected adapter failure"):
        guard._health_check()
    assert transport.aborted
    loop.call_later.assert_called_with(0.25, guard._health_check)


def test_health_callback_after_close_does_not_rearm_monitoring(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport],
) -> None:
    guard, source, loop, transport = setup_guard
    guard.start()
    assert guard.admit(transport)
    guard.close()
    loop.call_later.reset_mock()
    source.current.reset_mock()

    # A callback already queued when close() runs must not revive the timer.
    guard._health_check()

    loop.call_later.assert_not_called()
    source.current.assert_not_called()
    assert transport.aborted
    assert not guard.connections


def test_refresh_preserves_current_unexpired_connection(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport],
) -> None:
    guard, _source, _loop, transport = setup_guard
    assert guard.admit(transport)
    peer = guard.connections[transport]

    guard.refresh()

    assert guard.connections[transport] is peer
    assert not transport.aborted
    peer.timer.cancel.assert_not_called()
    assert guard.valid(transport)


@pytest.mark.asyncio
async def test_http_rotation_between_parse_and_task_dispatch_never_invokes_app() -> (
    None
):
    guard = Mock(spec=TransportGuard)
    guard.admit.return_value = True
    guard.valid.return_value = True
    guard.reject.side_effect = lambda transport: transport.abort()
    http, _ws = guarded_protocols(guard)
    app_called = False

    async def app(scope: object, receive: object, send: object) -> None:
        nonlocal app_called
        app_called = True

    config = Config(app=app, lifespan="off", log_config=None)
    config.load()
    state = ServerState()
    protocol = http(config, state, {})
    transport = Transport(None)
    protocol.connection_made(transport)
    protocol.data_received(b"GET / HTTP/1.1\r\nHost: ignored\r\n\r\n")
    pending = tuple(state.tasks)
    assert len(pending) == 1
    # No event-loop yield occurred: the app task is queued, not dispatched.
    guard.valid.return_value = False
    await asyncio.gather(*pending)
    assert not app_called
    assert transport.aborted
    assert protocol.cycle.disconnected
    protocol.connection_lost(None)


def test_peer_intermediate_expiry_limits_existing_connection(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport],
) -> None:
    guard, _source, loop, transport = setup_guard
    intermediate = leaf(
        ("spiffe://university.ecosystem/test-ca",),
        ca=True,
        key_cert_sign=True,
        valid_until=NOW + timedelta(seconds=20),
    )
    transport.tls.get_verified_chain.return_value = [
        transport.tls.getpeercert.return_value,
        intermediate.public_bytes(Encoding.DER),
    ]
    assert guard.admit(transport)
    assert loop.call_later.call_args.args[0] == 20


def test_missing_verified_chain_rejects_peer(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport],
) -> None:
    guard, _source, _loop, transport = setup_guard
    transport.tls.get_verified_chain.return_value = []
    assert not guard.admit(transport)
    assert transport.aborted


def test_watcher_notification_and_closed_guard_are_inert(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport],
) -> None:
    guard, source, loop, transport = setup_guard
    guard._updated()
    loop.call_soon_threadsafe.assert_called_once_with(guard.refresh)
    guard.close()
    source.current.reset_mock()
    guard._updated()
    guard.refresh()
    assert guard._client_hello(transport.tls, None, transport.tls.context) == (
        ssl.ALERT_DESCRIPTION_INTERNAL_ERROR
    )
    loop.call_soon_threadsafe.assert_called_once()
    source.current.assert_not_called()
    assert not guard.valid(transport)


@pytest.mark.parametrize("reason", ["untracked", "expired", "rotated", "closing"])
def test_valid_rejects_each_stale_authority_reason(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport], reason: str
) -> None:
    guard, source, _loop, transport = setup_guard
    if reason != "untracked":
        assert guard.admit(transport)
    if reason == "expired":
        peer = guard.connections[transport]
        guard.connections[transport] = transport_module.PeerConnection(
            peer.context, NOW - timedelta(seconds=1), peer.timer
        )
    elif reason == "rotated":
        source.current.return_value = TLSGeneration(
            ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER), b"new", NOW + timedelta(minutes=1)
        )
    elif reason == "closing":
        transport.abort()
    assert not guard.valid(transport)
    assert transport.aborted


@pytest.mark.parametrize("kind", ["http", "ws"])
def test_protocol_closes_non_transport_and_aborts_unadmitted(kind: str) -> None:
    guard = Mock(spec=TransportGuard)
    guard.admit.return_value = False
    classes = guarded_protocols(guard)
    protocol = object.__new__(classes[0 if kind == "http" else 1])
    invalid = Mock(spec=asyncio.BaseTransport)
    protocol.connection_made(invalid)
    invalid.close.assert_called_once()
    guard.admit.assert_not_called()
    transport = Transport(None)
    protocol.connection_made(transport)
    assert transport.aborted
    assert not protocol.admitted
    protocol.connection_lost(None)
    guard.remove.assert_called_once_with(transport)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["valid", "before_receive", "after_receive", "send"])
async def test_http_application_rechecks_receive_and_send(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    from unittest.mock import AsyncMock

    guard = Mock(spec=TransportGuard)
    guard.admit.return_value = True
    guard.valid.return_value = True
    guard.reject.side_effect = lambda transport: transport.abort()
    http, _ws = guarded_protocols(guard)
    protocol = object.__new__(http)
    protocol.cycle = Mock()
    received = []
    request = {"type": "http.request", "body": b"", "more_body": False}
    response = {"type": "http.response.start", "status": 200, "headers": []}
    receive = AsyncMock(return_value=request)
    send = AsyncMock()

    async def application(
        scope: object, guarded_receive: object, guarded_send: object
    ) -> None:
        if phase == "before_receive":
            guard.valid.return_value = False
        elif phase == "after_receive":

            async def revoke_during_receive() -> dict[str, object]:
                guard.valid.return_value = False
                return request

            receive.side_effect = revoke_during_receive
        received.append(await guarded_receive())
        if phase == "send":
            guard.valid.return_value = False
        await guarded_send(response)

    def base_connection_made(self: object, transport: object) -> None:
        self.app = application

    monkeypatch.setattr(
        transport_module.H11Protocol, "connection_made", base_connection_made
    )
    transport = Transport(None)
    protocol.connection_made(transport)
    await protocol.app({}, receive, send)
    if phase == "valid":
        assert received == [request]
        receive.assert_awaited_once()
        send.assert_awaited_once_with(response)
        assert not transport.aborted
        guard.reject.assert_not_called()
    else:
        assert transport.aborted
        assert protocol.cycle.disconnected
        protocol.cycle.message_event.set.assert_called()
        send.assert_not_awaited()
        if phase == "send":
            assert received == [request]
        else:
            assert received == [{"type": "http.disconnect"}]
        if phase == "before_receive":
            receive.assert_not_awaited()
        else:
            receive.assert_awaited_once()


@pytest.mark.asyncio
async def test_websocket_delegates_only_while_transport_is_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock

    guard = Mock(spec=TransportGuard)
    guard.valid.return_value = True
    _http, ws = guarded_protocols(guard)
    protocol = object.__new__(ws)
    protocol.admitted = True
    protocol.transport = Transport(None)
    base = transport_module.WebSocketsSansIOProtocol
    events = Mock()
    data = Mock()
    run = AsyncMock()
    receive = AsyncMock(return_value={"type": "websocket.receive", "text": "hello"})
    send = AsyncMock()
    monkeypatch.setattr(base, "data_received", data)
    monkeypatch.setattr(base, "handle_events", events)
    monkeypatch.setattr(base, "run_asgi", run)
    monkeypatch.setattr(base, "receive", receive)
    monkeypatch.setattr(base, "send", send)
    protocol.data_received(b"frame")
    data.assert_called_once_with(b"frame")
    protocol.handle_events()
    events.assert_called_once()
    await protocol.run_asgi()
    run.assert_awaited_once()
    assert await protocol.receive() == receive.return_value
    message = {"type": "websocket.send", "text": "reply"}
    await protocol.send(message)
    send.assert_awaited_once_with(message)
    guard.valid.return_value = False
    protocol.data_received(b"rejected")
    data.assert_called_once_with(b"frame")
    protocol.handle_events()
    await protocol.run_asgi()
    events.assert_called_once()
    run.assert_awaited_once()
    assert await protocol.receive() == {"type": "websocket.disconnect", "code": 1008}
    receive.assert_awaited_once()
    with pytest.raises(transport_module.ClientDisconnected):
        await protocol.send(message)
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_websocket_revocation_while_receive_is_pending_discards_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock

    guard = Mock(spec=TransportGuard)
    guard.valid.side_effect = [True, False]
    _http, ws = guarded_protocols(guard)
    protocol = object.__new__(ws)
    protocol.transport = Transport(None)
    receive = AsyncMock(return_value={"type": "websocket.receive", "text": "private"})
    monkeypatch.setattr(transport_module.WebSocketsSansIOProtocol, "receive", receive)
    assert await protocol.receive() == {"type": "websocket.disconnect", "code": 1008}
    receive.assert_awaited_once()
