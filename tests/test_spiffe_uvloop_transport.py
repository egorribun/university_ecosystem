"""Real TLS transports exercise the protocol boundary, without SPIRE issuance."""

from __future__ import annotations

import asyncio
import http.client
import ssl
import sys
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from uvicorn.config import Config
from uvicorn.server import ServerState
from websockets.asyncio.client import connect

import app.server.spiffe_transport as transport_module
from app.server.spiffe_identity import TLSGeneration, WorkloadContexts
from app.server.spiffe_transport import TransportGuard, guarded_protocols
from tests.test_spiffe_transport import Transport

SERVER_ID = "spiffe://university.ecosystem/ns/test/sa/backend"
CLIENT_ID = "spiffe://university.ecosystem/ns/test/sa/gateway"


class CompleteStreamTransport(Transport):
    """A fake with every stream method required by the production guard."""

    def __init__(self) -> None:
        super().__init__(None)
        self._protocol: asyncio.BaseProtocol | None = None
        self._reading = True
        self._write_buffer_limits = (0, 0)
        self._written: list[bytes] = []
        self._write_eof = False

    def set_protocol(self, protocol: asyncio.BaseProtocol) -> None:
        self._protocol = protocol

    def get_protocol(self) -> asyncio.BaseProtocol | None:
        return self._protocol

    def is_reading(self) -> bool:
        return self._reading

    def pause_reading(self) -> None:
        self._reading = False

    def resume_reading(self) -> None:
        self._reading = True

    def set_write_buffer_limits(
        self, high: int | None = None, low: int | None = None
    ) -> None:
        high = 65536 if high is None else high
        low = high // 4 if low is None else low
        self._write_buffer_limits = (high, low)

    def get_write_buffer_limits(self) -> tuple[int, int]:
        return self._write_buffer_limits

    def get_write_buffer_size(self) -> int:
        return sum(map(len, self._written))

    def write(self, data: bytes) -> None:
        self._written.append(data)

    def writelines(self, list_of_data: Iterable[bytes]) -> None:
        self._written.extend(list_of_data)

    def write_eof(self) -> None:
        self._write_eof = True

    def can_write_eof(self) -> bool:
        return True


@pytest.mark.parametrize("protocol_index", [0, 1])
@pytest.mark.parametrize(
    "missing_method",
    [
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
    ],
)
def test_incomplete_stream_interface_is_rejected_before_authorization(
    protocol_index: int, missing_method: str
) -> None:
    guard = Mock(spec=TransportGuard)
    guard.admit.return_value = False
    protocol_class = guarded_protocols(guard)[protocol_index]
    protocol = object.__new__(protocol_class)
    transport = CompleteStreamTransport()
    assert transport_module._stream_transport(transport) is transport
    setattr(transport, missing_method, "not-callable")
    assert transport_module._stream_transport(transport) is None
    protocol.connection_made(transport)
    guard.admit.assert_not_called()
    assert not protocol.admitted
    assert transport.aborted is (missing_method != "close")


@pytest.mark.parametrize("protocol_index", [0, 1])
def test_missing_stream_interface_is_rejected_without_dispatch(
    protocol_index: int,
) -> None:
    guard = Mock(spec=TransportGuard)
    protocol_class = guarded_protocols(guard)[protocol_index]
    protocol = object.__new__(protocol_class)
    protocol.connection_made(object())
    guard.admit.assert_not_called()
    assert not protocol.admitted


def _certificate(
    key: ec.EllipticCurvePrivateKey,
    issuer_key: ec.EllipticCurvePrivateKey,
    *,
    identity: str,
    ca: bool,
) -> x509.Certificate:
    now = datetime.now(UTC)
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-authority")])
    subject = issuer if ca else x509.Name([])
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(minutes=5))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(True, False, False, False, False, ca, ca, False, False),
            critical=True,
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.UniformResourceIdentifier(identity)]),
            critical=not ca,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()),
            critical=False,
        )
        .sign(issuer_key, hashes.SHA256())
    )


def _tls_contexts(
    tmp_path: Path, client_identity: str
) -> tuple[ssl.SSLContext, ssl.SSLContext]:
    authority_key = ec.generate_private_key(ec.SECP256R1())
    authority = _certificate(
        authority_key, authority_key, identity="spiffe://university.ecosystem", ca=True
    )
    contexts = []
    for name, identity, protocol in (
        ("server", SERVER_ID, ssl.PROTOCOL_TLS_SERVER),
        ("client", client_identity, ssl.PROTOCOL_TLS_CLIENT),
    ):
        key = ec.generate_private_key(ec.SECP256R1())
        certificate = _certificate(key, authority_key, identity=identity, ca=False)
        cert_path = tmp_path / f"{name}.pem"
        key_path = tmp_path / f"{name}-key.pem"
        cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        with key_path.open("xb") as stream:
            key_path.chmod(0o600)
            stream.write(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
        context = ssl.SSLContext(protocol)
        if name == "client":
            context.check_hostname = False
        context.verify_mode = ssl.CERT_REQUIRED
        context.verify_flags |= ssl.VERIFY_X509_STRICT
        context.options |= ssl.OP_NO_TICKET
        context.load_verify_locations(
            cadata=authority.public_bytes(serialization.Encoding.PEM).decode()
        )
        context.load_cert_chain(cert_path, key_path)
        contexts.append(context)
    return contexts[0], contexts[1]


@pytest.mark.parametrize("protocol", ["http", "websocket"])
@pytest.mark.parametrize("authorized", [True, False])
def test_real_event_loop_tls_transport_preserves_exact_identity_authorization(
    tmp_path: Path, protocol: str, authorized: bool
) -> None:
    server_context, client_context = _tls_contexts(
        tmp_path, CLIENT_ID if authorized else CLIENT_ID + "/wrong"
    )
    dispatched: list[str] = []

    async def application(scope, receive, send):
        dispatched.append(scope["type"])
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"authorized"})
        else:
            assert (await receive())["type"] == "websocket.connect"
            await send({"type": "websocket.accept"})
            message = await receive()
            await send({"type": "websocket.send", "text": message["text"]})
            await send({"type": "websocket.close", "code": 1000})

    async def exercise() -> None:
        loop = asyncio.get_running_loop()
        source = Mock(spec=WorkloadContexts)
        source.current.return_value = TLSGeneration(
            server_context, b"test-generation", datetime.now(UTC) + timedelta(minutes=5)
        )
        guard = TransportGuard(source, frozenset({CLIENT_ID}), loop)
        http_protocol, ws_protocol = guarded_protocols(guard)
        config = Config(
            application,
            http=http_protocol,
            ws=ws_protocol,
            lifespan="off",
            log_config=None,
        )
        config.load()
        state = ServerState()
        server = await loop.create_server(
            lambda: http_protocol(config=config, server_state=state, app_state={}),
            "127.0.0.1",
            0,
            ssl=guard.start(),
        )
        port = server.sockets[0].getsockname()[1]

        def request() -> bytes:
            connection = http.client.HTTPSConnection(
                "127.0.0.1", port, context=client_context, timeout=2
            )
            try:
                connection.request(
                    "GET", "/health/ready", headers={"Connection": "close"}
                )
                response = connection.getresponse()
                assert response.status == 200
                return response.read()
            finally:
                connection.close()

        try:
            if protocol == "http":
                if authorized:
                    assert await asyncio.to_thread(request) == b"authorized"
                else:
                    with pytest.raises((OSError, http.client.RemoteDisconnected)):
                        await asyncio.to_thread(request)
            else:
                from websockets.exceptions import InvalidHandshake

                if authorized:
                    async with connect(
                        f"wss://127.0.0.1:{port}/socket",
                        ssl=client_context,
                        open_timeout=2,
                    ) as websocket:
                        await websocket.send("authorized")
                        assert await websocket.recv() == "authorized"
                else:
                    with pytest.raises((OSError, InvalidHandshake)):
                        async with connect(
                            f"wss://127.0.0.1:{port}/socket",
                            ssl=client_context,
                            open_timeout=2,
                        ):
                            pytest.fail(
                                "unauthorized WebSocket reached the application"
                            )
            assert dispatched == ([protocol] if authorized else [])
        finally:
            guard.close()
            server.close()
            await server.wait_closed()
            if state.tasks:
                await asyncio.gather(*state.tasks)

    if sys.platform == "win32":
        asyncio.run(exercise())
    else:
        import uvloop

        uvloop.run(exercise())
