"""Exercise backend limiter middleware through real local TCP proxy hops.

The proxy fixtures model the forwarding operations of the edge and gateway.
They are not the deployed Caddy, Go gateway, Gunicorn, Redis, or Compose stack.
"""

from __future__ import annotations

import http.client
import secrets
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import SimpleQueue
from uuid import uuid4

import httpx
import pytest
import uvicorn
from fastapi import Depends, FastAPI, Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.core.middleware.setup import configure_middleware
from app.core.ratelimit import resolve_client_ip, sensitive_route_limit


@contextmanager
def _backend_server(app: ASGIApp) -> Iterator[int]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    config = uvicorn.Config(
        app, proxy_headers=False, lifespan="off", log_level="critical"
    )
    ready = threading.Event()

    class ObservedServer(uvicorn.Server):
        async def startup(self, sockets: list[socket.socket] | None = None) -> None:
            await super().startup(sockets=sockets)
            if self.started:
                ready.set()

    server = ObservedServer(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]})
    thread.start()
    try:
        assert ready.wait(10), "backend server did not start"
        yield port
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive(), "backend server did not stop"


@contextmanager
def _proxy_server(
    upstream_port: int, *, edge: bool
) -> Iterator[tuple[int, SimpleQueue[str]]]:
    peers: SimpleQueue[str] = SimpleQueue()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            self._forward()

        def do_POST(self) -> None:
            self._forward()

        def log_message(self, _format: str, *_args: object) -> None:
            pass

        def _forward(self) -> None:
            peer, peer_port = self.client_address
            peers.put(peer)
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            headers = {
                name: value
                for name, value in self.headers.items()
                if name.lower() not in {"connection", "host", "x-forwarded-for"}
                and (not edge or name.lower() != "x-real-ip")
            }
            headers["Host"] = "testserver"
            headers["Connection"] = "close"
            if edge:
                headers["X-Forwarded-For"] = peer
                headers["X-Real-IP"] = f"{peer}:{peer_port}"
            else:
                forwarded = self.headers.get("X-Forwarded-For")
                headers["X-Forwarded-For"] = (
                    f"{forwarded}, {peer}" if forwarded else peer
                )

            connection = http.client.HTTPConnection(
                "127.0.0.1", upstream_port, timeout=5
            )
            try:
                connection.request(self.command, self.path, body, headers)
                response = connection.getresponse()
                payload = response.read()
                self.send_response(response.status)
                for name, value in response.getheaders():
                    if name.lower() not in {
                        "connection",
                        "content-length",
                        "date",
                        "server",
                        "transfer-encoding",
                    }:
                        self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            finally:
                connection.close()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}
    )
    thread.start()
    try:
        yield server.server_address[1], peers
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive(), "proxy server did not stop"


def _client(source: str, port: int) -> httpx.Client:
    return httpx.Client(
        base_url=f"http://127.0.0.1:{port}",
        headers={"Host": "testserver"},
        transport=httpx.HTTPTransport(local_address=source, trust_env=False),
        timeout=5,
    )


@pytest.mark.parametrize(
    ("path", "uses_dependency"),
    [
        ("/api/v1/auth/login/json", False),
        ("/api/v1/auth/register", False),
        ("/api/v1/password/forgot", False),
        ("/api/v1/auth/mfa/verify", True),
    ],
    ids=("login", "registration", "password-reset", "mfa"),
)
def test_backend_separates_socket_clients_through_two_proxy_hops(
    monkeypatch: pytest.MonkeyPatch, path: str, uses_dependency: bool
) -> None:
    monkeypatch.setattr(settings, "trusted_proxies_list", ["127.0.0.1"])
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "memory")
    monkeypatch.setattr(settings, "rate_limit_storage_uri", "memory://")
    monkeypatch.setattr(settings, "rate_limit_default_list", ["200/minute"])
    monkeypatch.setattr(settings, "rate_limit_headers_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_auth_login", "2/minute")
    monkeypatch.setattr(settings, "rate_limit_auth_register", "2/minute")
    monkeypatch.setattr(settings, "rate_limit_auth_password_reset", "2/minute")
    monkeypatch.setattr(settings, "allowed_hosts_list", ["testserver"])
    monkeypatch.setattr(settings, "csrf_hmac_secret", secrets.token_urlsafe(32))

    app = FastAPI()
    dependencies = (
        [Depends(sensitive_route_limit(limit=2, window_sec=60, key_prefix=uuid4().hex))]
        if uses_dependency
        else []
    )

    @app.get("/api/v1/auth/csrf-cookie")
    async def csrf_cookie() -> dict[str, bool]:
        return {"ok": True}

    @app.post(path, dependencies=dependencies)
    async def limited(request: Request) -> dict[str, str]:
        assert request.client is not None
        return {
            "client": resolve_client_ip(request),
            "scope_client": request.client.host,
            "forwarded": request.headers.get("X-Forwarded-For", ""),
        }

    configure_middleware(app, settings)
    backend_peers: SimpleQueue[str] = SimpleQueue()

    async def record_socket_peer(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            peer = scope.get("client")
            assert peer is not None
            backend_peers.put(peer[0])
        await app(scope, receive, send)

    with (
        _backend_server(record_socket_peer) as backend_port,
        _proxy_server(backend_port, edge=False) as (gateway_port, gateway_peers),
        _proxy_server(gateway_port, edge=True) as (edge_port, edge_peers),
        _client("127.0.0.2", edge_port) as client_a,
        _client("127.0.0.3", edge_port) as client_b,
        _client("127.0.0.2", backend_port) as direct_a,
    ):
        for client in (client_a, client_b, direct_a):
            assert client.get("/api/v1/auth/csrf-cookie").status_code == 200
            csrf = client.cookies.get("csrf_token")
            assert csrf
            client.headers["X-CSRF-Token"] = csrf
        assert [edge_peers.get(timeout=5) for _ in range(2)] == [
            "127.0.0.2",
            "127.0.0.3",
        ]
        assert [gateway_peers.get(timeout=5) for _ in range(2)] == ["127.0.0.1"] * 2
        assert [backend_peers.get(timeout=5) for _ in range(3)] == [
            "127.0.0.1",
            "127.0.0.1",
            "127.0.0.2",
        ]

        started = time.monotonic()
        first = client_a.post(path, headers={"X-Forwarded-For": "127.0.0.3"})
        second = client_a.post(path, headers={"Forwarded": "for=127.0.0.3"})
        blocked = client_a.post(path)
        other = client_b.post(path)
        assert [edge_peers.get(timeout=5) for _ in range(4)] == [
            "127.0.0.2",
            "127.0.0.2",
            "127.0.0.2",
            "127.0.0.3",
        ]
        assert [gateway_peers.get(timeout=5) for _ in range(4)] == ["127.0.0.1"] * 4
        assert [backend_peers.get(timeout=5) for _ in range(4)] == ["127.0.0.1"] * 4
        assert [
            first.status_code,
            second.status_code,
            blocked.status_code,
            other.status_code,
        ] == [
            200,
            200,
            429,
            200,
        ]
        assert (
            first.json()
            == second.json()
            == {
                "client": "127.0.0.2",
                "scope_client": "127.0.0.2",
                "forwarded": "127.0.0.2, 127.0.0.1",
            }
        )
        assert other.json() == {
            "client": "127.0.0.3",
            "scope_client": "127.0.0.3",
            "forwarded": "127.0.0.3, 127.0.0.1",
        }

        for spoof in (
            {"X-Forwarded-For": "127.0.0.3"},
            {"X-Real-IP": "127.0.0.3"},
            {"Forwarded": "for=127.0.0.3"},
        ):
            assert client_a.post(path, headers=spoof).status_code == 429
            assert edge_peers.get(timeout=5) == "127.0.0.2"
            assert gateway_peers.get(timeout=5) == "127.0.0.1"
            assert backend_peers.get(timeout=5) == "127.0.0.1"
            assert direct_a.post(path, headers=spoof).status_code == 429
            assert backend_peers.get(timeout=5) == "127.0.0.2"
        assert time.monotonic() - started < 60
