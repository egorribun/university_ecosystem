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
