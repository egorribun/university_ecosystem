"""Actual worker/config/app forwarding contract with supplied ASGI scopes.

Construct the installed Gunicorn configuration and BackendWorker, then load its
actual Uvicorn configuration around configure_middleware. This includes both
ProxyHeadersMiddleware layers without starting a worker or server. C is a
client, F a forged prefix, E a hypothetical Envoy edge and G the Go gateway.

All addresses are documentation-only and supplied by ASGITransport. These tests
do not establish socket ownership, deployed proxy output, mTLS identities,
Envoy translation or deployment acceptance. Explicit outer trust is set through
Gunicorn Config.set, not environment parsing. The wildcard is a negative control,
not an approved setting or a production Helm bypass: staging/production reject
every nonempty backend.env and outboxWorker.env. No production source is changed.
"""

from __future__ import annotations

import logging
import os
import secrets
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, Request
from gunicorn.config import Config, ForwardedAllowIPS
from gunicorn.glogging import Logger
from starlette.types import ASGIApp, Receive, Scope, Send
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from uvicorn_worker import UvicornWorker

from app.core.config import settings
from app.core.middleware.setup import configure_middleware
from app.core.ratelimit import resolve_client_ip
from app.server.spiffe_worker import BackendWorker

_OBSERVE_PATH = "/api/v1/envoy-outer/observe"
_LIMITED_PATH = "/api/v1/auth/login/json"
_CSRF_PATH = "/api/v1/auth/csrf-cookie"

_ADDRESS_FAMILIES = (
    pytest.param(
        {
            "client_a": "192.0.2.10",
            "client_b": "198.51.100.10",
            "forged_a": "203.0.113.10",
            "forged_b": "203.0.113.11",
            "E": "198.51.100.20",
            "G": "203.0.113.20",
        },
        id="ipv4",
    ),
    pytest.param(
        {
            "client_a": "2001:db8:1::10",
            "client_b": "2001:db8:2::10",
            "forged_a": "2001:db8:3::10",
            "forged_b": "2001:db8:3::11",
            "E": "2001:db8:4::20",
            "G": "2001:db8:5::20",
        },
        id="ipv6",
    ),
)


@dataclass(frozen=True)
class _Case:
    name: str
    peer: str
    chain: tuple[str, ...]
    outer_trust: tuple[str, ...] | None
    app_trust: tuple[str, ...]
    after_outer: str
    after_app: str


_CASES = (
    _Case(
        "installed-default-complete-app-suffix",
        "G",
        ("F", "C", "E"),
        None,
        ("G", "E"),
        "G",
        "C",
    ),
    _Case(
        "explicit-complete-outer-suffix",
        "G",
        ("F", "C", "E"),
        ("G", "E"),
        ("G", "E"),
        "C",
        "C",
    ),
    _Case(
        "installed-default-incomplete-app-suffix",
        "G",
        ("F", "C", "E"),
        None,
        ("G",),
        "G",
        "E",
    ),
    _Case(
        "wildcard-outer-negative-control",
        "G",
        ("F", "C", "E"),
        ("*",),
        ("G", "E"),
        "F",
        "F",
    ),
    _Case(
        "installed-default-untrusted-direct-peer",
        "C",
        ("F", "E"),
        None,
        ("G", "E"),
        "C",
        "C",
    ),
)


@dataclass(frozen=True)
class _Observation:
    before_peer: tuple[str, int]
    before_headers: tuple[tuple[bytes, bytes], ...]
    after_peer: tuple[str, int]
    after_headers: tuple[tuple[bytes, bytes], ...]


class _Capture:
    """Snapshot scope boundaries without rewriting identity or headers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.observations: list[_Observation] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        assert scope["type"] == "http"
        before_peer = tuple(scope["client"])
        before_headers = tuple(scope["headers"])
        await self.app(scope, receive, send)
        self.observations.append(
            _Observation(
                before_peer,
                before_headers,
                tuple(scope["client"]),
                tuple(scope["headers"]),
            )
        )


@dataclass(frozen=True)
class _Stack:
    ingress: _Capture
    between_layers: _Capture


def _configured_app(monkeypatch: pytest.MonkeyPatch, trusted: list[str]) -> FastAPI:
    # Retain canonical autouse fixtures and the actual AUD-164 memory/CSRF setup.
    monkeypatch.setattr(settings, "trusted_proxies_list", trusted)
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "memory")
    monkeypatch.setattr(settings, "rate_limit_storage_uri", "memory://")
    monkeypatch.setattr(settings, "rate_limit_default_list", ["200/minute"])
    monkeypatch.setattr(settings, "rate_limit_headers_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_auth_login", "2/minute")
    monkeypatch.setattr(settings, "allowed_hosts_list", ["testserver"])
    monkeypatch.setattr(settings, "csrf_hmac_secret", secrets.token_urlsafe(32))
    app = FastAPI()

    @app.get(_CSRF_PATH)
    async def csrf_cookie() -> dict[str, bool]:
        return {"ok": True}

    @app.get(_OBSERVE_PATH)
    @app.post(_LIMITED_PATH)
    async def observed(request: Request) -> dict[str, object]:
        return {
            "scope_client": list(request.scope["client"]),
            "resolved_client": resolve_client_ip(request),
        }

    configure_middleware(app, settings)
    return app


def _deny_socket_operation(*args: object, **kwargs: object) -> None:
    raise AssertionError("This in-process contract must not bind, listen or connect")


@contextmanager
def _loaded_stack(
    app: FastAPI, case: _Case, addresses: dict[str, str], tmp_path: Path
) -> Iterator[_Stack]:
    # Gunicorn captures the environment in ForwardedAllowIPS.default at import.
    # Check both the actual default and Config value; do not delete the env after
    # import or model the installed parser. No environment override is tested.
    assert "FORWARDED_ALLOW_IPS" not in os.environ
    assert ForwardedAllowIPS.default == "127.0.0.1,::1"
    cfg = Config()
    assert cfg.forwarded_allow_ips == ["127.0.0.1", "::1"]
    assert cfg.accesslog is None
    assert cfg.errorlog == "-"
    assert not cfg.syslog and not cfg.capture_output and not cfg.is_ssl
    assert (cfg.uid, cfg.gid) == (os.geteuid(), os.getegid())
    cfg.set("worker_tmp_dir", str(tmp_path))
    if case.outer_trust is not None:
        cfg.set(
            "forwarded_allow_ips",
            ",".join(addresses.get(role, role) for role in case.outer_trust),
        )

    loggers = [
        logging.getLogger(name)
        for name in (
            "gunicorn.error",
            "gunicorn.access",
            "uvicorn.error",
            "uvicorn.access",
        )
    ]
    saved = [
        (logger, logger.handlers, logger.level, logger.propagate) for logger in loggers
    ]
    worker: BackendWorker | None = None
    with pytest.MonkeyPatch.context() as guard:
        for method in ("bind", "listen", "connect", "connect_ex"):
            guard.setattr(socket.socket, method, _deny_socket_operation)
        try:
            # Logger setup mutates handler lists. Preserve the originals, restore
            # levels/propagation, and close only handlers created by this context.
            for logger in loggers:
                logger.handlers = list(logger.handlers)
            assert BackendWorker.__init__ is UvicornWorker.__init__
            worker = BackendWorker(0, os.getpid(), [], None, 30, cfg, Logger(cfg))
            assert worker.config.forwarded_allow_ips == cfg.forwarded_allow_ips
            assert worker.config.proxy_headers is True
            between = _Capture(app)
            # Mirror the application attachment from _serve, but never call
            # _serve/init_process/run or create a Server/WorkloadContexts source.
            worker.wsgi = between
            worker.config.app = worker.wsgi
            worker.config.load()
            assert worker.config.loaded is True
            assert isinstance(worker.config.loaded_app, ProxyHeadersMiddleware)
            assert worker.config.loaded_app.app is between
            yield _Stack(_Capture(worker.config.loaded_app), between)
        finally:
            try:
                if worker is not None:
                    worker.tmp.close()
                    assert worker.tmp._tmp.closed
            finally:
                original_handlers = {h for _, handlers, _, _ in saved for h in handlers}
                created_handlers = {
                    h for logger in loggers for h in logger.handlers
                } - original_handlers
                for logger, handlers, level, propagate in saved:
                    logger.handlers = handlers
                    logger.setLevel(level)
                    logger.propagate = propagate
                for handler in created_handlers:
                    handler.close()


def _roles(addresses: dict[str, str], client: str, forged: str) -> dict[str, str]:
    assert len(set(addresses.values())) == len(addresses)
    return {**addresses, "C": addresses[client], "F": addresses[forged]}


def _headers(
    case: _Case, roles: dict[str, str], *, repeated: bool
) -> list[tuple[str, str]]:
    chain = [roles[role] for role in case.chain]
    if repeated:
        return [("X-Forwarded-For", hop) for hop in chain]
    return [("X-Forwarded-For", ", ".join(chain))]


def _assert_boundaries(
    stack: _Stack,
    response: httpx.Response,
    case: _Case,
    roles: dict[str, str],
    headers: list[tuple[str, str]],
) -> None:
    ingress = stack.ingress.observations[-1]
    between = stack.between_layers.observations[-1]
    supplied_peer = (roles[case.peer], 50001)
    outer_port = 50001 if case.after_outer == case.peer else 0
    final_port = 50001 if case.peer == "C" else 0
    final_peer = (roles[case.after_app], final_port)
    assert ingress.before_peer == supplied_peer
    assert between.before_peer == (roles[case.after_outer], outer_port)
    assert ingress.after_peer == between.after_peer == final_peer
    assert (
        ingress.before_headers
        == between.before_headers
        == between.after_headers
        == ingress.after_headers
    )
    assert [
        (name, value)
        for name, value in ingress.before_headers
        if name == b"x-forwarded-for"
    ] == [(name.lower().encode(), value.encode()) for name, value in headers]
    if response.status_code == 200:
        # The endpoint witnesses the real stack's client and actual resolver.
        assert response.json() == {
            "scope_client": list(final_peer),
            "resolved_client": roles[case.after_app],
        }


@pytest.mark.parametrize("addresses", _ADDRESS_FAMILIES)
@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("repeated", [False, True], ids=["joined-XFF", "repeated-XFF"])
@pytest.mark.asyncio
async def test_worker_loaded_stack_witnesses_both_proxy_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    addresses: dict[str, str],
    case: _Case,
    repeated: bool,
) -> None:
    app = _configured_app(monkeypatch, [addresses[role] for role in case.app_trust])
    with _loaded_stack(app, case, addresses, tmp_path) as stack:
        for client in ("client_a", "client_b"):
            roles = _roles(addresses, client, "forged_a")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(
                    app=stack.ingress, client=(roles[case.peer], 50001)
                ),
                base_url="https://testserver",
            ) as requester:
                for forged in ("forged_a", "forged_b"):
                    roles = _roles(addresses, client, forged)
                    headers = _headers(case, roles, repeated=repeated)
                    response = await requester.get(_OBSERVE_PATH, headers=headers)
                    assert response.status_code == 200
                    _assert_boundaries(stack, response, case, roles, headers)


@pytest.mark.parametrize("addresses", _ADDRESS_FAMILIES)
@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
@pytest.mark.asyncio
async def test_worker_loaded_real_limiter_distinguishes_trust_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    addresses: dict[str, str],
    case: _Case,
) -> None:
    app = _configured_app(monkeypatch, [addresses[role] for role in case.app_trust])
    with _loaded_stack(app, case, addresses, tmp_path) as stack:
        for client in ("client_a", "client_b"):
            roles = _roles(addresses, client, "forged_a")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(
                    app=stack.ingress, client=(roles[case.peer], 50001)
                ),
                base_url="https://testserver",
            ) as requester:
                setup = await requester.get(
                    _CSRF_PATH, headers=_headers(case, roles, repeated=False)
                )
                assert setup.status_code == 200
                csrf = requester.cookies.get("csrf_token")
                assert csrf
                requester.headers["X-CSRF-Token"] = csrf
                responses = []
                for forged, repeated in (
                    ("forged_a", False),
                    ("forged_a", True),
                    ("forged_a", False),
                    ("forged_b", True),
                ):
                    roles = _roles(addresses, client, forged)
                    headers = _headers(case, roles, repeated=repeated)
                    response = await requester.post(_LIMITED_PATH, headers=headers)
                    _assert_boundaries(stack, response, case, roles, headers)
                    assert response.headers["X-RateLimit-Limit"] == "2"
                    responses.append(response.status_code)

            if case.after_app == "C":
                # Each real client owns a separate bucket; changing F cannot
                # escape exhaustion, whether direct or via the trusted suffix.
                assert responses == [200, 200, 429, 429]
            elif case.after_app == "E":
                # Omitting E from app trust collapses both clients onto E.
                expected = [200, 200, 429, 429] if client == "client_a" else [429] * 4
                assert responses == expected
            else:
                assert case.after_app == "F"
                # Wildcard outer trust selects F before app verification. The
                # forged bucket is shared and changing F escapes its exhaustion.
                expected = (
                    [200, 200, 429, 200] if client == "client_a" else [429] * 3 + [200]
                )
                assert responses == expected
