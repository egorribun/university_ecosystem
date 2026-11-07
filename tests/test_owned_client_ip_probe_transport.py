"""Real loopback boundaries for the fixed owned probe transport."""

from __future__ import annotations

import errno
import socket
import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace

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
                    # Observe peer EOF/reset separately from the writer: on
                    # Windows a failed write can also be a local socket abort.
                    def send_drip() -> None:
                        try:
                            for byte in reply:
                                if stop.wait(0.02) or closed.is_set():
                                    return
                                self.request.sendall(bytes([byte]))
                        except OSError as error:
                            if error.errno not in {
                                errno.EPIPE,
                                errno.ECONNRESET,
                                errno.ENOTCONN,
                                errno.ECONNABORTED,
                            } or not closed.wait(2):
                                failures.append(True)

                    writer = threading.Thread(target=send_drip, name="drip-writer")
                    writer.start()
                    try:
                        try:
                            received = self.request.recv(1)
                        except OSError as error:
                            if error.errno == errno.ECONNRESET:
                                closed.set()
                            else:
                                failures.append(True)
                        else:
                            if received == b"":
                                closed.set()
                            else:
                                failures.append(True)
                    finally:
                        stop.set()
                        writer.join(timeout=5)
                        if writer.is_alive():
                            failures.append(True)
                    return
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


def test_rolling_timeout_negative_control(monkeypatch: pytest.MonkeyPatch) -> None:
    reply = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"
    with _reply_server(reply, drip=True) as (port, seen, closed):
        monkeypatch.setattr(probe, "_remaining", lambda _deadline: 0.5)
        response = probe._request(_request(port), 0.5)
        assert response.status == 200 and response.body == b"ok"
        assert len(seen) == 1 and closed.wait(2)


def test_peer_observer_rejects_an_open_connection() -> None:
    reply = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"
    with _reply_server(reply, drip=True) as (port, seen, closed):
        connection = socket.create_connection(("127.0.0.1", port), timeout=5)
        try:
            connection.sendall(
                b"GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
            )
            assert connection.recv(1) == b"H"
            assert len(seen) == 1
            assert not closed.wait(0.15)
        finally:
            connection.close()
        assert closed.wait(2)


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


def _post(cookie: str) -> probe.Request:
    return probe.Request(
        "172.23.0.10",
        "172.23.0.20",
        80,
        "POST",
        "/api/v1/auth/login/json",
        (("cookie", cookie), ("x-csrf-token", "token")),
        b"{}",
    )


@pytest.mark.parametrize(
    "cookie",
    [
        "csrf_token=token; _csrf_anon_nonce=nonce;session_id=fixture",
        "csrf_token=token;session_id=fixture; _csrf_anon_nonce=nonce",
        "csrf_token=token; _csrf_anon_nonce=nonce; session_id=fixture",
        "csrf_token=token; _csrf_anon_nonce=nonce\r\nHost: example.invalid",
    ],
    ids=[
        "hidden-after-nonce",
        "hidden-after-token",
        "third-cookie",
        "header-injection",
    ],
)
def test_post_encoder_rejects_hidden_or_injected_cookie_fields(cookie: str) -> None:
    # The real encoder must first accept the fixed anonymous request.
    valid = _post("csrf_token=token; _csrf_anon_nonce=nonce")
    wire = probe._request_bytes(valid)
    assert wire.startswith(b"POST /api/v1/auth/login/json HTTP/1.1\r\n")
    assert b"cookie: csrf_token=token; _csrf_anon_nonce=nonce\r\n" in wire
    assert b"Content-Length: 2\r\n" in wire
    assert wire.endswith(b"\r\n\r\n{}")

    with pytest.raises(probe.ProbeError):
        probe._request_bytes(_post(cookie))


@pytest.mark.parametrize(
    "timeout",
    [10**1000, float("nan"), float("inf"), 0, 6, True],
    ids=["huge-integer", "nan", "infinity", "zero", "over-budget", "boolean"],
)
def test_invalid_timeout_is_closed_before_socket_creation(
    monkeypatch: pytest.MonkeyPatch, timeout: float
) -> None:
    request = _request(1)
    assert probe._request_bytes(request).startswith(b"GET / HTTP/1.1\r\n")

    def unexpected_socket(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid timeout reached socket creation")

    # Replace only this module's view, not the process-global socket module.
    guarded = SimpleNamespace(**vars(probe.socket))
    guarded.socket = unexpected_socket
    monkeypatch.setattr(probe, "socket", guarded)
    with pytest.raises(probe.ProbeError):
        probe._request(request, timeout)
