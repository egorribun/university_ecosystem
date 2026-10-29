"""Real loopback boundaries for the fixed owned probe transport."""

from __future__ import annotations

import errno
import socket
import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from scripts import owned_client_ip_probe as probe


@contextmanager
def _reply_server(
    reply: bytes, *, drip: bool = False
) -> Iterator[tuple[int, list[tuple[str, bytes]], threading.Event]]:
    seen: list[tuple[str, bytes]] = []
    closed = threading.Event()
    stop = threading.Event()
    failures: list[bool] = []

    class Handler(socketserver.BaseRequestHandler):
        def handle(self) -> None:
            self.request.settimeout(5)
            request = bytearray()
            try:
                while b"\r\n\r\n" not in request and len(request) <= 8192:
                    part = self.request.recv(1024)
                    if not part:
                        return
                    request.extend(part)
                seen.append((self.client_address[0], bytes(request)))
                if drip:
                    for byte in reply:
                        if stop.wait(0.02):
                            return
                        self.request.sendall(bytes([byte]))
                else:
                    self.request.sendall(reply)
                self.request.shutdown(socket.SHUT_WR)
                if self.request.recv(1) == b"":
                    closed.set()
            except OSError as error:
                if error.errno in {errno.EPIPE, errno.ECONNRESET, errno.ENOTCONN}:
                    closed.set()
                else:
                    raise

    class Server(socketserver.TCPServer):
        def handle_error(self, _request: object, _address: object) -> None:
            failures.append(True)

    server = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=lambda: server.serve_forever(poll_interval=0.01),
        name="owned-probe-response-fixture",
    )
    thread.start()
    try:
        yield server.server_address[1], seen, closed
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert not failures


def _request(port: int) -> probe.Request:
    return probe.Request("127.0.0.2", "127.0.0.1", port, "GET", "/", (), b"")


@pytest.mark.parametrize(
    ("reply", "body"),
    [
        (b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok", b"ok"),
        (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
            b"2\r\nok\r\n0\r\n\r\n",
            b"ok",
        ),
        (
            b"HTTP/1.1 200 OK\r\nContent-Length: 4096\r\n\r\n" + b"x" * 4096,
            b"x" * 4096,
        ),
        (
            b"HTTP/1.1 100 Continue\r\n\r\n"
            b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok",
            b"ok",
        ),
    ],
    ids=["content-length", "chunked", "body-at-limit", "interim-then-final"],
)
def test_transport_binds_actual_secondary_loopback_and_closes_from_client(
    reply: bytes, body: bytes
) -> None:
    with _reply_server(reply) as (port, seen, closed):
        response = probe._request(_request(port), 5)
        assert response.body == body
        assert response.source_verified and response.closed
        assert closed.wait(2)
        assert len(seen) == 1 and seen[0][0] == "127.0.0.2"
        assert seen[0][1].startswith(b"GET / HTTP/1.1\r\n")
        assert b"Connection: close\r\n" in seen[0][1]


@pytest.mark.parametrize(
    "reply",
    [
        b"HTTP/1.1 200 OK\r\nContent-Length: 4097\r\n\r\n" + b"x" * 4097,
        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nx",
        b"HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Length: 1\r\n\r\nx",
        b"HTTP/1.1 200 OK\r\nContent-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\n",
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: gzip\r\n\r\n",
        b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: 0\r\n\r\n",
        b"HTTP/1.1 200 OK\r\nX-Large: " + b"x" * 16385 + b"\r\n\r\n",
        b"HTTP/1.1 200 OK\r\nX-Folded: one\r\n two\r\nContent-Length: 0\r\n\r\n",
        b"HTTP/1.1 101 Switching Protocols\r\nContent-Length: 0\r\n\r\n",
        (
            b"HTTP/1.1 100 Continue\r\n\r\n" * 1100
            + b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
        ),
        (
            b"HTTP/1.1 200 OK\r\nSet-Cookie: session_id=fixture\r\n"
            b"Content-Length: 0\r\n\r\n"
        ),
    ],
    ids=[
        "oversized-body",
        "truncated-body",
        "duplicate-length",
        "ambiguous-framing",
        "unsupported-transfer",
        "compressed-body",
        "oversized-headers",
        "folded-header",
        "upgrade",
        "unbounded-interim-responses",
        "authenticated-cookie",
    ],
)
def test_malformed_or_unbounded_response_cannot_return_a_receipt(reply: bytes) -> None:
    with _reply_server(reply) as (port, seen, closed):
        with pytest.raises(probe.ProbeError):
            probe._request(_request(port), 5)
        assert len(seen) == 1 and closed.wait(2)


def test_transport_deadline_does_not_restart_for_each_header_byte() -> None:
    reply = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"
    with _reply_server(reply, drip=True) as (port, seen, closed):
        with pytest.raises(probe.ProbeError):
            probe._request(_request(port), 0.5)
        assert len(seen) == 1 and closed.wait(2)


def test_redirect_is_observed_once_and_never_followed() -> None:
    target_reply = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
    with _reply_server(target_reply) as (target_port, target_seen, _target_closed):
        reply = (
            b"HTTP/1.1 302 Found\r\n"
            + f"Location: http://127.0.0.1:{target_port}/\r\n".encode("ascii")
            + b"Content-Length: 0\r\n\r\n"
        )
        with _reply_server(reply) as (port, seen, closed):
            response = probe._request(_request(port), 5)
            assert response.status == 302 and response.body == b""
            assert response.closed and closed.wait(2)
            assert len(seen) == 1
            assert target_seen == []
