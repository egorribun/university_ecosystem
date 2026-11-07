"""Fail-closed transport authorization and rotation for backend HTTP and WS."""

from __future__ import annotations

import asyncio
import re
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from cryptography import x509
from spiffe.errors import ArgumentError
from spiffe.workloadapi.errors import X509SourceError
from uvicorn._types import (
    ASGI3Application,
    ASGIReceiveCallable,
    ASGIReceiveEvent,
    ASGISendCallable,
    ASGISendEvent,
    Scope,
)
from uvicorn.protocols.http.h11_impl import H11Protocol
from uvicorn.protocols.utils import ClientDisconnected
from uvicorn.protocols.websockets.websockets_sansio_impl import WebSocketsSansIOProtocol

from app.core.logging import get_logger
from app.server.spiffe_identity import (
    TLSGeneration,
    WorkloadContexts,
    WorkloadIdentityError,
    authorize_verified_leaf,
    chain_deadline,
)

_FAILURES = (
    WorkloadIdentityError,
    X509SourceError,
    ArgumentError,
    ValueError,
    OSError,
    x509.DuplicateExtension,
    x509.UnsupportedGeneralNameType,
)
_HEALTH_INTERVAL = 0.25
logger = get_logger(__name__)


class HandshakeDiagnostics:
    """Opt-in, finite proof telemetry; never a TLS authorization decision."""

    def __init__(self) -> None:
        self.remaining = 64
        observer = self

        class ObservedSSLObject(ssl.SSLObject):
            probe_id: str | None = None
            hello_seen: bool = False

            def do_handshake(self) -> None:
                try:
                    super().do_handshake()
                except ssl.SSLError as error:
                    try:
                        observer.record(self, error)
                    finally:
                        # Telemetry must never replace or suppress the TLS failure.
                        raise error

        self.sslobject_class = ObservedSSLObject

    def client_hello(
        self, connection: ssl.SSLSocket | ssl.SSLObject, name: str | None
    ) -> None:
        if isinstance(connection, self.sslobject_class):
            if connection.hello_seen:
                # Ambiguous/repeated ClientHello is not usable correlation evidence.
                connection.probe_id = None
                return
            connection.hello_seen = True
            connection.probe_id = None
            if name is not None and re.fullmatch(r"aud373-[0-9a-f]{32}\.invalid", name):
                connection.probe_id = name[7:-8]

    def record(self, connection: ssl.SSLObject, error: ssl.SSLError) -> None:
        if (
            not isinstance(connection, self.sslobject_class)
            or connection.probe_id is None
            or error.reason != "PEER_DID_NOT_RETURN_A_CERTIFICATE"
            or self.remaining == 0
        ):
            return
        probe_id = connection.probe_id
        connection.probe_id = None
        self.remaining -= 1
        logger.warning(
            "internal_mtls_handshake_rejected",
            probe_id=str(UUID(hex=probe_id)),
            reason="PEER_DID_NOT_RETURN_A_CERTIFICATE",
        )


def _stream_transport(transport: asyncio.BaseTransport) -> asyncio.Transport | None:
    # uvloop's TLS transport implements asyncio's stream contract without
    # inheriting asyncio.Transport. This checks the interface only; TLS chain,
    # exact identity and generation authorization remain in TransportGuard.
    methods = (
        "get_extra_info",
        "is_closing",
        "close",
        "set_protocol",
        "get_protocol",
        "is_reading",
        "pause_reading",
        "resume_reading",
        "set_write_buffer_limits",
        "get_write_buffer_limits",
        "get_write_buffer_size",
        "write",
        "writelines",
        "write_eof",
        "can_write_eof",
        "abort",
    )
    if not all(callable(getattr(transport, method, None)) for method in methods):
        return None
    return cast(asyncio.Transport, transport)


@dataclass(frozen=True, slots=True)
class PeerConnection:
    """A verified connection tied to one immutable trust generation."""

    context: ssl.SSLContext
    expires_at: datetime
    timer: asyncio.TimerHandle


class TransportGuard:
    """Own transport lifetime separately from H11/WS protocol registries."""

    def __init__(
        self,
        source: WorkloadContexts,
        allowed: frozenset[str],
        loop: asyncio.AbstractEventLoop,
        *,
        handshake_diagnostics: bool = False,
    ) -> None:
        self.diagnostics = HandshakeDiagnostics() if handshake_diagnostics else None
        self.source = source
        self.allowed = allowed
        self.loop = loop
        self.connections: dict[asyncio.Transport, PeerConnection] = {}
        self._armed: ssl.SSLContext | None = None
        self._closed = False
        self._health_timer: asyncio.TimerHandle | None = None
        self.source.subscribe(self._updated)

    def _updated(self) -> None:
        # SDK invokes this on its watcher thread. Only the loop owns transports.
        if not self._closed:
            self.loop.call_soon_threadsafe(self.refresh)

    def context(self) -> TLSGeneration:
        generation = self.source.current()
        if generation.context is not self._armed:
            # A newly built context has not served a connection yet. Configure
            # its callback once, before publication, including TLS1.3 retries.
            if self.diagnostics is not None:
                generation.context.sslobject_class = self.diagnostics.sslobject_class
            generation.context.sni_callback = self._client_hello
            self._armed = generation.context
        return generation

    def _client_hello(
        self,
        connection: ssl.SSLSocket | ssl.SSLObject,
        _server_name: str | None,
        _initial: ssl.SSLContext,
    ) -> int | None:
        if self._closed:
            return ssl.ALERT_DESCRIPTION_INTERNAL_ERROR
        try:
            connection.context = self.context().context
            if self.diagnostics is not None:
                self.diagnostics.client_hello(connection, _server_name)
        except _FAILURES:
            return ssl.ALERT_DESCRIPTION_ACCESS_DENIED
        return None

    def start(self) -> ssl.SSLContext:
        """Initialize before Server.serve can accept any application connection."""
        initial = self.context().context
        self._health_timer = self.loop.call_later(_HEALTH_INTERVAL, self._health_check)
        return initial

    def _health_check(self) -> None:
        try:
            self.refresh()
        finally:
            if not self._closed:
                self._health_timer = self.loop.call_later(
                    _HEALTH_INTERVAL, self._health_check
                )

    def refresh(self) -> None:
        """Retire old generations, including already-upgraded WebSockets."""
        if self._closed:
            return
        current: TLSGeneration | None = None
        try:
            current = self.context()
        except _FAILURES:
            return
        finally:
            # Unexpected SDK/adapter failures also retire authority, while the
            # original exception propagates instead of a broad catch hiding it.
            if current is None:
                self.abort_all()
        now = datetime.now(UTC)
        for transport, peer in tuple(self.connections.items()):
            if peer.context is not current.context or now >= peer.expires_at:
                self.reject(transport)

    def admit(self, transport: asyncio.Transport) -> bool:
        """Chain has been checked by TLS; authorize its actual peer certificate."""
        if self._closed:
            transport.abort()
            return False
        approved = False
        try:
            generation = self.context()
            tls = transport.get_extra_info("ssl_object")
            if not isinstance(tls, ssl.SSLObject):
                raise WorkloadIdentityError("a TLS transport is required")
            if tls.context is not generation.context or tls.session_reused:
                raise WorkloadIdentityError("fresh current-generation TLS is required")
            if tls.context.verify_mode != ssl.CERT_REQUIRED:
                raise WorkloadIdentityError("mutual TLS verification is required")
            der = tls.getpeercert(binary_form=True)
            if not der:
                raise WorkloadIdentityError("peer certificate is missing")
            certificate = x509.load_der_x509_certificate(der)
            now = datetime.now(UTC)
            verified_chain = tls.get_verified_chain()
            if not verified_chain or verified_chain[0] != der:
                raise WorkloadIdentityError(
                    "verified chain does not contain the peer leaf"
                )
            peer_deadline = chain_deadline(
                [x509.load_der_x509_certificate(item) for item in verified_chain], now
            )
            peer_spiffe_id = authorize_verified_leaf(certificate, self.allowed, now)
            expires = min(peer_deadline, generation.expires_at)
            approved = True
        except _FAILURES as error:
            # Reasons are fixed WorkloadIdentityError messages or exception class
            # names only: never certificate bytes, headers or request data.
            logger.warning(
                "internal_mtls_peer_rejected",
                reason=type(error).__name__,
                detail=str(error) if isinstance(error, WorkloadIdentityError) else "",
            )
            return False
        finally:
            if not approved:
                self.reject(transport)
        # Only the authorized SPIFFE ID is logged: no certificate, header or request data.
        logger.info("internal_mtls_peer_authorized", peer_spiffe_id=peer_spiffe_id)
        # H11 upgrades call the WS connection_made with this same transport.
        # Replacing its record must not leave a timer referring to the old one.
        self.remove(transport)
        timer = self.loop.call_later(
            max(0.0, (expires - now).total_seconds()), self.reject, transport
        )
        self.connections[transport] = PeerConnection(generation.context, expires, timer)
        return True

    def valid(self, transport: asyncio.Transport) -> bool:
        if self._closed or transport.is_closing():
            return False
        peer = self.connections.get(transport)
        try:
            generation = self.context()
        except _FAILURES:
            self.reject(transport)
            return False
        if (
            peer is None
            or peer.context is not generation.context
            or datetime.now(UTC) >= peer.expires_at
        ):
            self.reject(transport)
            return False
        return True

    def remove(self, transport: asyncio.Transport) -> None:
        peer = self.connections.pop(transport, None)
        if peer is not None:
            peer.timer.cancel()

    def reject(self, transport: asyncio.Transport) -> None:
        self.remove(transport)
        transport.abort()

    def abort_all(self) -> None:
        for transport in tuple(self.connections):
            self.reject(transport)

    def close(self) -> None:
        self._closed = True
        self.source.unsubscribe(self._updated)
        if self._health_timer is not None:
            self._health_timer.cancel()
        self.abort_all()


def guarded_protocols(
    guard: TransportGuard,
) -> tuple[type[H11Protocol], type[WebSocketsSansIOProtocol]]:
    """Bind transport authority, never HTTP headers, into protocol instances."""

    class GuardedHTTP(H11Protocol):
        admitted = False

        def connection_made(self, transport: asyncio.BaseTransport) -> None:
            stream = _stream_transport(transport)
            if stream is None:
                close = getattr(transport, "close", None)
                if callable(close):
                    close()
                return
            transport = stream
            self.transport = transport
            try:
                self.admitted = guard.admit(transport)
            finally:
                if not self.admitted:
                    transport.abort()
            if self.admitted:
                super().connection_made(transport)
                application: ASGI3Application = self.app

                async def authorized_application(
                    scope: Scope,
                    receive: ASGIReceiveCallable,
                    send: ASGISendCallable,
                ) -> None:
                    # H11 schedules run_asgi as a later task. Recheck at actual
                    # coroutine entry, not just when HTTP bytes were parsed.
                    if not guard.valid(self.transport):
                        self.disconnect_cycle()
                        return

                    async def authorized_receive() -> ASGIReceiveEvent:
                        if not guard.valid(self.transport):
                            self.disconnect_cycle()
                            return {"type": "http.disconnect"}
                        message = await receive()
                        if not guard.valid(self.transport):
                            self.disconnect_cycle()
                            return {"type": "http.disconnect"}
                        return message

                    async def authorized_send(message: ASGISendEvent) -> None:
                        if not guard.valid(self.transport):
                            self.disconnect_cycle()
                            return
                        await send(message)

                    await application(scope, authorized_receive, authorized_send)

                self.app = authorized_application

        def disconnect_cycle(self) -> None:
            # Called only after H11 has created its RequestResponseCycle. Mark
            # disconnection synchronously so run_asgi does not log a missing
            # response while asyncio is still delivering connection_lost.
            self.cycle.disconnected = True
            self.cycle.message_event.set()
            guard.reject(self.transport)

        def data_received(self, data: bytes) -> None:
            if self.admitted and guard.valid(self.transport):
                super().data_received(data)

        def handle_events(self) -> None:
            # Includes buffered HTTP pipelining from on_response_complete().
            if self.admitted and guard.valid(self.transport):
                super().handle_events()

        def connection_lost(self, exc: Exception | None) -> None:
            guard.remove(self.transport)
            if self.admitted:
                super().connection_lost(exc)

    class GuardedWebSocket(WebSocketsSansIOProtocol):
        admitted = False

        def connection_made(self, transport: asyncio.BaseTransport) -> None:
            stream = _stream_transport(transport)
            if stream is None:
                close = getattr(transport, "close", None)
                if callable(close):
                    close()
                return
            transport = stream
            self.transport = transport
            try:
                self.admitted = guard.admit(transport)
            finally:
                if not self.admitted:
                    transport.abort()
            if self.admitted:
                super().connection_made(transport)

        def data_received(self, data: bytes) -> None:
            if self.admitted and guard.valid(self.transport):
                super().data_received(data)

        def handle_events(self) -> None:
            if self.admitted and guard.valid(self.transport):
                super().handle_events()

        async def run_asgi(self) -> None:
            if self.admitted and guard.valid(self.transport):
                await super().run_asgi()

        async def receive(self) -> ASGIReceiveEvent:
            if not guard.valid(self.transport):
                return {"type": "websocket.disconnect", "code": 1008}
            message = await super().receive()
            if not guard.valid(self.transport):
                return {"type": "websocket.disconnect", "code": 1008}
            return message

        async def send(self, message: ASGISendEvent) -> None:
            if not guard.valid(self.transport):
                raise ClientDisconnected()
            await super().send(message)

        def connection_lost(self, exc: Exception | None) -> None:
            guard.remove(self.transport)
            if self.admitted:
                super().connection_lost(exc)

    return GuardedHTTP, GuardedWebSocket
