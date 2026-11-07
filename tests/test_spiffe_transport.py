"""Protocol lifecycle controls with mocked TLS; not a cryptographic proof."""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import Callable
from datetime import timedelta
from unittest.mock import Mock, call

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


def test_admission_logs_only_the_authorized_peer_spiffe_id_once(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard, _source, _loop, transport = setup_guard
    logger = Mock()
    monkeypatch.setattr(transport_module, "logger", logger)
    assert guard.start() is not None
    assert guard.admit(transport)
    assert logger.info.call_args_list == [
        call("internal_mtls_peer_authorized", peer_spiffe_id=IDENTITY)
    ]


def test_rejected_peer_is_never_logged_as_authorized(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard, _source, _loop, transport = setup_guard
    logger = Mock()
    monkeypatch.setattr(transport_module, "logger", logger)
    transport.tls.getpeercert.return_value = leaf((IDENTITY + "/other",)).public_bytes(
        Encoding.DER
    )
    assert not guard.admit(transport)
    logger.info.assert_not_called()


def _without_peer_certificate(tls: Mock) -> None:
    tls.getpeercert.return_value = None


def _session_reused(tls: Mock) -> None:
    tls.session_reused = True


def _empty_verified_chain(tls: Mock) -> None:
    tls.get_verified_chain.return_value = []


@pytest.mark.parametrize(
    ("mutate", "detail"),
    [
        (_without_peer_certificate, "peer certificate is missing"),
        (_session_reused, "fresh current-generation TLS is required"),
        (_empty_verified_chain, "verified chain does not contain the peer leaf"),
    ],
)
def test_rejection_logs_reason_without_certificate_data(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport],
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[Mock], None],
    detail: str,
) -> None:
    guard, _source, _loop, transport = setup_guard
    logger = Mock()
    monkeypatch.setattr(transport_module, "logger", logger)
    assert guard.start() is not None
    mutate(transport.tls)
    assert not guard.admit(transport)
    assert logger.warning.call_args == call(
        "internal_mtls_peer_rejected",
        reason="WorkloadIdentityError",
        detail=detail,
    )
    assert transport.aborted
    logger.info.assert_not_called()


def test_rejection_logs_exception_class_for_unexpected_verifier_failure(
    setup_guard: tuple[TransportGuard, Mock, Mock, Transport],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard, _source, _loop, transport = setup_guard
    logger = Mock()
    monkeypatch.setattr(transport_module, "logger", logger)
    transport.tls.getpeercert.side_effect = OSError("socket closed")
    assert not guard.admit(transport)
    assert logger.warning.call_args == call(
        "internal_mtls_peer_rejected", reason="OSError", detail=""
    )


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


def _diagnostic_connection(
    observer: transport_module.HandshakeDiagnostics,
) -> ssl.SSLObject:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.sslobject_class = observer.sslobject_class
    return context.wrap_bio(ssl.MemoryBIO(), ssl.MemoryBIO(), server_side=True)


def _missing_certificate() -> ssl.SSLError:
    error = ssl.SSLError("deliberately private error text")
    error.reason = "PEER_DID_NOT_RETURN_A_CERTIFICATE"
    return error


@pytest.mark.parametrize(
    "name",
    [
        None,
        "",
        "localhost",
        "aud373-short.invalid",
        "aud373-" + "A" * 32 + ".invalid",
        "aud373-" + "0" * 32 + ".invalid\nsecret",
    ],
)
def test_handshake_diagnostics_reject_unbounded_or_unrelated_sni(monkeypatch, name):
    observer = transport_module.HandshakeDiagnostics()
    connection = _diagnostic_connection(observer)
    logger = Mock()
    monkeypatch.setattr(transport_module, "logger", logger)
    observer.client_hello(connection, name)
    observer.record(connection, _missing_certificate())
    logger.warning.assert_not_called()
    assert observer.remaining == 64


def test_handshake_diagnostics_bound_and_deduplicate_events(monkeypatch):
    observer = transport_module.HandshakeDiagnostics()
    logger = Mock()
    monkeypatch.setattr(transport_module, "logger", logger)
    for index in range(70):
        connection = _diagnostic_connection(observer)
        nonce = f"{index:032x}"
        observer.client_hello(connection, f"aud373-{nonce}.invalid")
        observer.record(connection, _missing_certificate())
        observer.record(connection, _missing_certificate())
    assert observer.remaining == 0
    assert logger.warning.call_count == 64
    assert logger.warning.call_args_list[0] == call(
        "internal_mtls_handshake_rejected",
        probe_id="-".join("0" * count for count in (8, 4, 4, 4, 12)),
        reason="PEER_DID_NOT_RETURN_A_CERTIFICATE",
    )
    assert "deliberately private" not in str(logger.mock_calls)


def test_handshake_diagnostics_ignore_other_tls_reasons(monkeypatch):
    observer = transport_module.HandshakeDiagnostics()
    connection = _diagnostic_connection(observer)
    logger = Mock()
    monkeypatch.setattr(transport_module, "logger", logger)
    observer.client_hello(connection, "aud373-" + "0" * 32 + ".invalid")
    error = ssl.SSLError("private")
    error.reason = "WRONG_VERSION_NUMBER"
    observer.record(connection, error)
    logger.warning.assert_not_called()


def test_handshake_diagnostics_never_replace_original_tls_exception(monkeypatch):
    observer = transport_module.HandshakeDiagnostics()
    connection = _diagnostic_connection(observer)
    original = _missing_certificate()

    def reject(_self):
        raise original

    def broken_observer(*_args):
        raise RuntimeError("telemetry unavailable")

    monkeypatch.setattr(ssl.SSLObject, "do_handshake", reject)
    monkeypatch.setattr(observer, "record", broken_observer)
    with pytest.raises(ssl.SSLError) as caught:
        connection.do_handshake()
    assert caught.value is original


@pytest.mark.parametrize("second", ["0", "1"])
def test_repeated_client_hello_disables_correlation(monkeypatch, second):
    observer = transport_module.HandshakeDiagnostics()
    connection = _diagnostic_connection(observer)
    logger = Mock()
    monkeypatch.setattr(transport_module, "logger", logger)
    observer.client_hello(connection, "aud373-" + "0" * 32 + ".invalid")
    observer.client_hello(connection, "aud373-" + second * 32 + ".invalid")
    observer.record(connection, _missing_certificate())
    logger.warning.assert_not_called()


def test_handshake_diagnostics_disabled_by_default(setup_guard):
    guard, _source, _loop, _transport = setup_guard
    assert guard.diagnostics is None
    assert guard.start().sslobject_class is ssl.SSLObject


def test_handshake_diagnostics_installed_on_new_context(setup_guard):
    _guard, source, loop, _transport = setup_guard
    diagnostic_guard = TransportGuard(
        source, frozenset({IDENTITY}), loop, handshake_diagnostics=True
    )
    first = diagnostic_guard.start()
    assert diagnostic_guard.diagnostics is not None
    observer_class = diagnostic_guard.diagnostics.sslobject_class
    assert first.sslobject_class is observer_class
    replacement = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    replacement.verify_mode = ssl.CERT_REQUIRED
    source.current.return_value = TLSGeneration(
        replacement, b"rotated", NOW + timedelta(minutes=1)
    )
    assert diagnostic_guard.context().context.sslobject_class is observer_class
    assert replacement.sni_callback == diagnostic_guard._client_hello


def test_diagnostic_sni_callback_correlates_without_changing_tls_authority(
    setup_guard, monkeypatch
):
    _guard, source, loop, _transport = setup_guard
    guard = TransportGuard(
        source, frozenset({IDENTITY}), loop, handshake_diagnostics=True
    )
    try:
        initial = guard.start()
        observer = guard.diagnostics
        assert observer is not None
        connection = initial.wrap_bio(
            ssl.MemoryBIO(), ssl.MemoryBIO(), server_side=True
        )
        replacement = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        replacement.verify_mode = ssl.CERT_REQUIRED
        source.current.return_value = TLSGeneration(
            replacement, b"rotated", NOW + timedelta(minutes=1)
        )
        callback = initial.sni_callback
        assert callback is not None
        assert callback(connection, "aud373-" + "0" * 32 + ".invalid", initial) is None
        assert connection.context is replacement
        assert connection.context.verify_mode == ssl.CERT_REQUIRED
        assert connection.probe_id == "0" * 32
        assert connection.hello_seen
        emit = Mock()
        monkeypatch.setattr(transport_module.logger, "warning", emit)
        error = ssl.SSLError("private TLS failure")
        error.reason = "PEER_DID_NOT_RETURN_A_CERTIFICATE"
        observer.record(connection, error)
        emit.assert_called_once_with(
            "internal_mtls_handshake_rejected",
            probe_id="00000000-0000-0000-0000-000000000000",
            reason="PEER_DID_NOT_RETURN_A_CERTIFICATE",
        )
        assert connection.probe_id is None
    finally:
        guard.close()


@pytest.mark.parametrize("foreign_observer", [False, True])
def test_handshake_diagnostics_do_not_claim_connections_they_do_not_own(
    monkeypatch, foreign_observer
):
    observer = transport_module.HandshakeDiagnostics()
    owner = transport_module.HandshakeDiagnostics()
    if foreign_observer:
        connection = _diagnostic_connection(owner)
        owner.client_hello(connection, "aud373-" + "a" * 32 + ".invalid")
    else:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        connection = context.wrap_bio(
            ssl.MemoryBIO(), ssl.MemoryBIO(), server_side=True
        )
    initial_context = connection.context
    logger = Mock()
    monkeypatch.setattr(transport_module, "logger", logger)
    observer.client_hello(connection, "aud373-" + "b" * 32 + ".invalid")
    observer.record(connection, _missing_certificate())
    assert connection.context is initial_context
    assert observer.remaining == 64
    logger.warning.assert_not_called()
    if foreign_observer:
        assert connection.probe_id == "a" * 32
        owner.record(connection, _missing_certificate())
        logger.warning.assert_called_once_with(
            "internal_mtls_handshake_rejected",
            probe_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            reason="PEER_DID_NOT_RETURN_A_CERTIFICATE",
        )
