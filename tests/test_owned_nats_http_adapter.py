from __future__ import annotations

import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from scripts import owned_nats_http_adapter as http_adapter
from scripts.owned_nats_coordinator import (
    ChatCreateEvidence,
    LoginEvidence,
    MessagePostEvidence,
    OwnerEvidence,
    ParticipantEvidence,
)
from scripts.owned_nats_outage import Deadline, MessageEvidence
from scripts.owned_nats_owner_adapter import OwnerFilePins

ADMIN_ID = "11111111-1111-4111-8111-111111111111"
PEER_ID = "22222222-2222-4222-8222-222222222222"
CHAT_ID = "33333333-3333-4333-8333-333333333333"
MESSAGE_ID = "44444444-4444-4444-8444-444444444444"
CONTENT = "owned NATS acceptance probe"
PASSWORD = secrets.token_urlsafe(32)
BODY_TOKEN = "synthetic-body-bearer-token"
COOKIE_TOKEN = "synthetic-http-only-cookie-token"


class _MockBodyStream(httpx.AsyncByteStream):
    def __init__(self, body: bytes) -> None:
        self.body = body

    async def __aiter__(self):
        for offset in range(0, len(self.body), 4096):
            yield self.body[offset : offset + 4096]

    async def aclose(self) -> None:
        return


class _Clock:
    def __init__(self) -> None:
        self.now = 10.0

    def __call__(self) -> float:
        return self.now


class _OwnerReader:
    def __init__(self, owner: OwnerEvidence) -> None:
        self.owner = owner
        self.deadlines: list[Deadline] = []
        self.owner_changes: dict[int, OwnerEvidence] = {}

    def read_signed_owner(self, *, deadline: Deadline) -> OwnerEvidence:
        self.deadlines.append(deadline)
        changed = self.owner_changes.get(len(self.deadlines))
        if changed is not None:
            self.owner = changed
        return self.owner


@pytest.fixture
def setup_case(tmp_path: Path, request: pytest.FixtureRequest):
    repository = tmp_path / "repository"
    worktree = repository / "run"
    secrets_dir = worktree / ".secrets"
    secrets_dir.mkdir(parents=True)
    owner = OwnerEvidence(
        repository=str(repository.resolve()),
        worktree=str(worktree.resolve()),
        project_name="ue-live-0123456789abcdef",
        published_ports=(("CADDY_HTTP", 23111),),
        schema_version=11,
        daemon_fingerprint="a" * 64,
        compose_resource_fingerprint="b" * 64,
        resume_compose_resource_fingerprint=None,
        resume_compose_resource_schema_version=None,
        source_sha="c" * 40,
        stack="full",
        service_roots=("backend", "caddy"),
        selected_services=("backend", "caddy"),
    )
    pins = OwnerFilePins(
        repository=str(repository.resolve()),
        state_root=str(worktree.resolve()),
        source_sha="c" * 40,
        owner_uid=os.getuid() if hasattr(os, "getuid") else 0,
    )
    _write_credential(worktree, owner.project_name)
    clock = _Clock()
    deadline = Deadline.after(30, clock=clock)
    reader = _OwnerReader(owner)
    requests: list[httpx.Request] = []
    csrf_mode = {"value": "success"}
    login_mode = {"value": "success"}
    create_mode = {"value": "success"}
    send_mode = {"value": "success"}
    expire_on_csrf = {"value": False}

    def response_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path == "/api/v1/auth/csrf-cookie":
            if csrf_mode["value"] == "redirect":
                return httpx.Response(
                    302, headers={"location": "https://example.invalid/"}
                )
            if csrf_mode["value"] == "missing-cookie":
                return httpx.Response(200, json={"detail": "CSRF cookie set"})
            response = httpx.Response(
                200,
                headers=[
                    ("set-cookie", "csrf_token=csrf-before; Path=/; SameSite=Strict"),
                    ("set-cookie", "_csrf_anon_nonce=nonce; Path=/; HttpOnly"),
                ],
                json={"detail": "CSRF cookie set"},
            )
            if expire_on_csrf["value"]:
                clock.now = deadline.expires_at  # type: ignore[assignment]
            return response
        if path == "/api/v1/auth/login":
            mode = login_mode["value"]
            if mode == "mfa":
                return httpx.Response(200, json={"mfa_required": True})
            if mode == "wrong-actor":
                actor = PEER_ID
            else:
                actor = ADMIN_ID
            cookies = [("set-cookie", "csrf_token=csrf-after; Path=/; SameSite=Strict")]
            if mode not in {"missing-cookie", "mfa"}:
                http_only = "; HttpOnly" if mode != "non-http-only" else ""
                secure = "; Secure" if mode == "secure-cookie" else ""
                cookies.append(
                    (
                        "set-cookie",
                        f"access_token_v2={COOKIE_TOKEN}; Path=/{http_only}{secure}; SameSite=Strict",
                    )
                )
            return httpx.Response(
                200,
                headers=cookies,
                json={
                    "access_token": BODY_TOKEN,
                    "token_type": "bearer",
                    "user": {"id": actor},
                },
            )
        if path == "/api/v1/chats":
            if create_mode["value"] == "unavailable":
                return httpx.Response(503, json={"detail": "unavailable"})
            if create_mode["value"] == "oversized":
                return httpx.Response(200, json={"untrusted": "x" * 70_000})
            participants = [
                {"id": ADMIN_ID, "is_active": True},
                {"id": PEER_ID, "is_active": True},
            ]
            if create_mode["value"] == "foreign":
                participants[1]["id"] = "55555555-5555-4555-8555-555555555555"
            elif create_mode["value"] == "duplicate":
                participants[1]["id"] = ADMIN_ID
            elif create_mode["value"] == "inactive":
                participants[1]["is_active"] = False
            return httpx.Response(
                200,
                json={
                    "id": CHAT_ID,
                    "chat_type": "dm",
                    "participants": participants,
                },
            )
        if path == f"/api/v1/chats/{CHAT_ID}/messages":
            if send_mode["value"] == "timeout":
                raise httpx.ReadTimeout("synthetic transport detail", request=request)
            content = (
                "wrong message" if send_mode["value"] == "wrong-content" else CONTENT
            )
            reply_to = {"id": MESSAGE_ID} if send_mode["value"] == "reply" else None
            return httpx.Response(
                200,
                json={
                    "id": MESSAGE_ID,
                    "chat_id": CHAT_ID,
                    "sender_id": ADMIN_ID,
                    "content": content,
                    "reply_to": reply_to,
                },
            )
        return httpx.Response(404)

    def handler(request: httpx.Request) -> httpx.Response:
        response = response_handler(request)
        body = response.content
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            stream=_MockBodyStream(body),
            request=request,
        )

    adapter = http_adapter.OwnedNatsHttpPort(
        reader,
        pins,
        transport=httpx.MockTransport(handler),
    )
    request.addfinalizer(lambda: adapter.close_clients(deadline=deadline))
    return {
        "adapter": adapter,
        "clock": clock,
        "deadline": deadline,
        "owner": owner,
        "reader": reader,
        "requests": requests,
        "csrf_mode": csrf_mode,
        "login_mode": login_mode,
        "create_mode": create_mode,
        "send_mode": send_mode,
        "expire_on_csrf": expire_on_csrf,
        "worktree": worktree,
    }


def _write_credential(
    worktree: Path, project_name: str, password: str = PASSWORD
) -> None:
    secrets_dir = worktree / ".secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    path = secrets_dir / "live-admin-password.json"
    path.write_text(
        json.dumps({"version": 1, "project_name": project_name, "password": password}),
        encoding="utf-8",
    )
    if os.name != "nt":
        secrets_dir.chmod(0o700)
        path.chmod(0o600)


def _form(request: httpx.Request) -> dict[str, list[str]]:
    return parse_qs(request.content.decode("ascii"))


def _login(case: dict[str, object]) -> LoginEvidence:
    return case["adapter"].login_admin(  # type: ignore[union-attr]
        case["owner"],
        ADMIN_ID,
        deadline=case["deadline"],  # type: ignore[arg-type]
    )


def _create(case: dict[str, object]) -> ChatCreateEvidence:
    return case["adapter"].create_dm_once(  # type: ignore[union-attr]
        PEER_ID,
        deadline=case["deadline"],  # type: ignore[arg-type]
    )


def _send(case: dict[str, object]) -> MessagePostEvidence:
    return case["adapter"].send_message_once(  # type: ignore[union-attr]
        CHAT_ID,
        CONTENT,
        deadline=case["deadline"],  # type: ignore[arg-type]
    )


def test_happy_path_uses_rotated_csrf_and_cookie_auth_only(
    setup_case, monkeypatch, capsys
) -> None:
    case = setup_case
    adapter = case["adapter"]
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *_args, **_kwargs: pytest.fail("credential must use a bounded fd read"),
    )
    read_sizes: list[int] = []
    original_read = os.read

    def bounded_read(descriptor: int, size: int) -> bytes:
        read_sizes.append(size)
        assert size <= http_adapter._READ_CHUNK_BYTES
        return original_read(descriptor, size)

    monkeypatch.setattr(http_adapter.os, "read", bounded_read)

    assert _login(case) == LoginEvidence(status_code=200, actor_id=ADMIN_ID)
    login_deadlines = list(case["reader"].deadlines)
    assert _create(case) == ChatCreateEvidence(
        status_code=200,
        id=CHAT_ID,
        chat_type="dm",
        participants=(
            ParticipantEvidence(id=ADMIN_ID, is_active=True),
            ParticipantEvidence(id=PEER_ID, is_active=True),
        ),
    )
    assert _send(case) == MessagePostEvidence(
        status_code=200,
        message=MessageEvidence(MESSAGE_ID, CHAT_ID, ADMIN_ID, CONTENT),
    )

    requests = case["requests"]
    assert [request.url.path for request in requests] == [
        "/api/v1/auth/csrf-cookie",
        "/api/v1/auth/login",
        "/api/v1/chats",
        f"/api/v1/chats/{CHAT_ID}/messages",
    ]
    login_request, create_request, send_request = requests[1:]
    assert _form(login_request) == {
        "username": ["admin@university.dev"],
        "password": [PASSWORD],
    }
    assert login_request.headers["x-csrf-token"] == "csrf-before"
    assert "csrf_token=csrf-before" in login_request.headers["cookie"]
    assert create_request.headers["x-csrf-token"] == "csrf-after"
    assert "csrf_token=csrf-after" in create_request.headers["cookie"]
    assert f"access_token_v2={COOKIE_TOKEN}" in create_request.headers["cookie"]
    assert json.loads(create_request.content) == {"participant_id": PEER_ID}
    assert send_request.headers["x-csrf-token"] == "csrf-after"
    assert f"access_token_v2={COOKIE_TOKEN}" in send_request.headers["cookie"]
    assert send_request.headers["content-type"].startswith("multipart/form-data;")
    assert send_request.content.count(b"Content-Disposition:") == 1
    assert b'name="content"' in send_request.content
    assert CONTENT.encode() in send_request.content
    assert all("authorization" not in request.headers for request in requests)
    assert all(
        request.extensions["timeout"]["read"] <= http_adapter._HTTP_READ_POLL_SECONDS
        for request in requests
    )
    cookie = next(
        cookie for cookie in adapter._cookies.jar if cookie.name == "access_token_v2"
    )
    assert cookie.has_nonstandard_attr("HttpOnly")
    assert read_sizes and all(
        size <= http_adapter._READ_CHUNK_BYTES for size in read_sizes
    )
    assert all(request.url.host == "127.0.0.1" for request in requests)
    assert all(request.url.port == 23111 for request in requests)
    assert BODY_TOKEN not in repr(adapter)
    assert COOKIE_TOKEN not in repr(adapter)
    assert PASSWORD not in repr(adapter)
    assert not hasattr(adapter, "_password")
    assert all(
        item._clock is case["deadline"]._clock
        and item.expires_at <= case["deadline"].expires_at
        for item in case["reader"].deadlines
    )
    assert len({id(item) for item in login_deadlines}) == 1
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize(
    "login_mode",
    ["mfa", "missing-cookie", "non-http-only", "secure-cookie", "wrong-actor"],
)
def test_login_rejects_mfa_bad_cookie_or_wrong_actor_without_creating_chat(
    setup_case, login_mode: str
) -> None:
    case = setup_case
    case["login_mode"]["value"] = login_mode  # type: ignore[index]
    with pytest.raises(http_adapter.HttpObservationNotReady) as caught:
        _login(case)
    assert str(caught.value) == "owner-scoped HTTP observation is not ready"
    assert len(case["requests"]) == 2
    assert all(request.url.path != "/api/v1/chats" for request in case["requests"])
    assert PASSWORD not in str(caught.value)
    assert BODY_TOKEN not in str(caught.value)
    if login_mode == "wrong-actor":
        with pytest.raises(http_adapter.HttpObservationNotReady):
            _create(case)
        assert all(request.url.path != "/api/v1/chats" for request in case["requests"])


def test_owner_drift_before_login_performs_no_http_request(setup_case) -> None:
    case = setup_case
    changed = case["owner"].__class__(
        **{**case["owner"].__dict__, "project_name": "ue-live-fedcba9876543210"}
    )
    case["reader"].owner = changed
    with pytest.raises(http_adapter.HttpObservationNotReady):
        _login(case)
    assert case["requests"] == []


def test_create_chat_ambiguous_failure_is_never_retried(setup_case) -> None:
    case = setup_case
    _login(case)
    case["create_mode"]["value"] = "unavailable"  # type: ignore[index]
    with pytest.raises(http_adapter.HttpObservationNotReady):
        _create(case)
    with pytest.raises(http_adapter.HttpObservationNotReady):
        _create(case)
    assert case["adapter"]._closed
    assert list(case["adapter"]._cookies.jar) == []
    assert [request.url.path for request in case["requests"]].count(
        "/api/v1/chats"
    ) == 1


def test_message_timeout_is_never_retried_and_error_is_redacted(setup_case) -> None:
    case = setup_case
    _login(case)
    _create(case)
    case["send_mode"]["value"] = "timeout"  # type: ignore[index]
    with pytest.raises(http_adapter.HttpObservationNotReady) as caught:
        _send(case)
    assert str(caught.value) == "owner-scoped HTTP observation is not ready"
    assert case["adapter"]._closed
    assert list(case["adapter"]._cookies.jar) == []
    with pytest.raises(http_adapter.HttpObservationNotReady):
        _send(case)
    assert [request.url.path for request in case["requests"]].count(
        f"/api/v1/chats/{CHAT_ID}/messages"
    ) == 1
    assert "synthetic transport detail" not in str(caught.value)


def test_credential_owner_mismatch_and_oversize_fail_before_http(setup_case) -> None:
    case = setup_case
    _write_credential(case["worktree"], "ue-live-wrong-project")  # type: ignore[arg-type]
    with pytest.raises(http_adapter.HttpObservationNotReady):
        _login(case)
    assert case["requests"] == []

    case = setup_case
    _write_credential(
        case["worktree"],
        case["owner"].project_name,
        "x" * 20_000,  # type: ignore[index,arg-type]
    )
    with pytest.raises(http_adapter.HttpObservationNotReady):
        _login(case)
    assert case["requests"] == []


@pytest.mark.parametrize(
    "create_mode", ["foreign", "duplicate", "inactive", "oversized"]
)
def test_create_rejects_unbound_or_unbounded_chat_response_without_retry(
    setup_case, create_mode: str
) -> None:
    case = setup_case
    _login(case)
    case["create_mode"]["value"] = create_mode  # type: ignore[index]
    with pytest.raises(http_adapter.HttpObservationNotReady):
        _create(case)
    with pytest.raises(http_adapter.HttpObservationNotReady):
        _create(case)
    assert [request.url.path for request in case["requests"]].count(
        "/api/v1/chats"
    ) == 1
    assert all(
        not request.url.path.endswith(f"/chats/{CHAT_ID}/messages")
        for request in case["requests"]
    )


@pytest.mark.parametrize("send_mode", ["wrong-content", "reply"])
def test_message_response_must_match_single_form_send_without_retry(
    setup_case, send_mode: str
) -> None:
    case = setup_case
    _login(case)
    _create(case)
    case["send_mode"]["value"] = send_mode  # type: ignore[index]
    with pytest.raises(http_adapter.HttpObservationNotReady):
        _send(case)
    with pytest.raises(http_adapter.HttpObservationNotReady):
        _send(case)
    assert [request.url.path for request in case["requests"]].count(
        f"/api/v1/chats/{CHAT_ID}/messages"
    ) == 1


def test_redirect_and_missing_initial_csrf_cookie_never_continue(setup_case) -> None:
    case = setup_case
    case["csrf_mode"]["value"] = "redirect"  # type: ignore[index]
    with pytest.raises(http_adapter.HttpObservationNotReady):
        _login(case)
    assert [request.url.path for request in case["requests"]] == [
        "/api/v1/auth/csrf-cookie"
    ]
    assert case["requests"][0].url.host == "127.0.0.1"

    case = setup_case
    case["csrf_mode"]["value"] = "missing-cookie"  # type: ignore[index]
    with pytest.raises(http_adapter.HttpObservationNotReady):
        _login(case)
    assert [request.url.path for request in case["requests"]] == [
        "/api/v1/auth/csrf-cookie"
    ]


def test_owner_drift_after_csrf_get_prevents_credential_login_post(setup_case) -> None:
    case = setup_case
    changed = case["owner"].__class__(
        **{**case["owner"].__dict__, "project_name": "ue-live-fedcba9876543210"}
    )
    # Owner reads are: login admission, credential open, credential close,
    # before GET, then after GET. Drift at the last check must stop login.
    case["reader"].owner_changes[5] = changed  # type: ignore[index,union-attr]
    with pytest.raises(http_adapter.HttpObservationNotReady):
        _login(case)
    assert [request.url.path for request in case["requests"]] == [
        "/api/v1/auth/csrf-cookie"
    ]


def test_close_clears_cookie_jar_and_prevents_future_http(setup_case) -> None:
    case = setup_case
    _login(case)
    adapter = case["adapter"]
    assert len(list(adapter._cookies.jar)) >= 2
    adapter.close_clients(deadline=case["deadline"])
    assert list(adapter._cookies.jar) == []
    assert not adapter._verified_login
    before = len(case["requests"])
    with pytest.raises(http_adapter.HttpObservationNotReady):
        _create(case)
    assert len(case["requests"]) == before


def test_deadline_expiring_after_csrf_get_prevents_login_post(setup_case) -> None:
    case = setup_case
    case["expire_on_csrf"]["value"] = True  # type: ignore[index]
    with pytest.raises(http_adapter.HttpObservationNotReady):
        _login(case)
    assert [request.url.path for request in case["requests"]] == [
        "/api/v1/auth/csrf-cookie"
    ]


def _local_http_handler(
    requests: list[tuple[str, str]],
    *,
    trickle_started: threading.Event | None = None,
    stop_trickle: threading.Event | None = None,
):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _json(self, status: int, body: dict[str, object], headers=()) -> None:
            encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            for name, value in headers:
                self.send_header(name, value)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:
            requests.append(("GET", self.path))
            if self.path == "/api/v1/auth/csrf-cookie":
                self._json(
                    200,
                    {"detail": "CSRF cookie set"},
                    (
                        (
                            "Set-Cookie",
                            "csrf_token=csrf-local-before; Path=/; SameSite=Strict",
                        ),
                        ("Set-Cookie", "_csrf_anon_nonce=nonce; Path=/; HttpOnly"),
                    ),
                )
                return
            self._json(404, {"detail": "missing"})

        def do_POST(self) -> None:
            requests.append(("POST", self.path))
            length = int(self.headers.get("content-length", "0"))
            payload = self.rfile.read(length)
            if self.path == "/api/v1/auth/login":
                assert parse_qs(payload.decode("ascii")) == {
                    "username": ["admin@university.dev"],
                    "password": [PASSWORD],
                }
                assert self.headers.get("x-csrf-token") == "csrf-local-before"
                self._json(
                    200,
                    {"user": {"id": ADMIN_ID}},
                    (
                        (
                            "Set-Cookie",
                            "csrf_token=csrf-local-after; Path=/; SameSite=Strict",
                        ),
                        (
                            "Set-Cookie",
                            f"access_token_v2={COOKIE_TOKEN}; Path=/; HttpOnly; SameSite=Strict",
                        ),
                    ),
                )
                return
            if self.path == "/api/v1/chats":
                assert self.headers.get("x-csrf-token") == "csrf-local-after"
                assert f"access_token_v2={COOKIE_TOKEN}" in self.headers.get(
                    "cookie", ""
                )
                assert json.loads(payload) == {"participant_id": PEER_ID}
                self._json(
                    200,
                    {
                        "id": CHAT_ID,
                        "chat_type": "dm",
                        "participants": [
                            {"id": ADMIN_ID, "is_active": True},
                            {"id": PEER_ID, "is_active": True},
                        ],
                    },
                )
                return
            if self.path == f"/api/v1/chats/{CHAT_ID}/messages":
                assert self.headers.get("x-csrf-token") == "csrf-local-after"
                assert f"access_token_v2={COOKIE_TOKEN}" in self.headers.get(
                    "cookie", ""
                )
                assert b'name="content"' in payload and CONTENT.encode() in payload
                self._json(
                    200,
                    {
                        "id": MESSAGE_ID,
                        "chat_id": CHAT_ID,
                        "sender_id": ADMIN_ID,
                        "content": CONTENT,
                        "reply_to": None,
                        "attachments": [],
                    },
                )
                return
            self._json(404, {"detail": "missing"})

    if trickle_started is not None and stop_trickle is not None:
        original_do_get = Handler.do_GET

        def trickle_get(self) -> None:
            if self.path != "/api/v1/auth/csrf-cookie":
                original_do_get(self)
                return
            requests.append(("GET", self.path))
            self.wfile.write(b"HTTP/1.1 200 OK\r\nX-Slow-Header: ")
            self.wfile.flush()
            trickle_started.set()
            for _ in range(20):
                if stop_trickle.wait(0.05):
                    return
                try:
                    self.wfile.write(b"x")
                    self.wfile.flush()
                except OSError:
                    return
            try:
                self.wfile.write(
                    b"\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}"
                )
                self.wfile.flush()
            except OSError:
                return

        Handler.do_GET = trickle_get
    return Handler


def _local_server(handler) -> tuple[ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_sequential_local_login_create_send_works_across_asyncio_loops(
    setup_case,
) -> None:
    case = setup_case
    observed: list[tuple[str, str]] = []
    server, thread = _local_server(_local_http_handler(observed))
    original_owner = case["owner"]
    owner = original_owner.__class__(
        **{
            **original_owner.__dict__,
            "published_ports": (("CADDY_HTTP", server.server_port),),
        }
    )
    case["reader"].owner = owner
    adapter = http_adapter.OwnedNatsHttpPort(case["reader"], case["adapter"]._pins)
    try:
        assert (
            adapter.login_admin(owner, ADMIN_ID, deadline=case["deadline"]).actor_id
            == ADMIN_ID
        )
        assert adapter.create_dm_once(PEER_ID, deadline=case["deadline"]).id == CHAT_ID
        assert (
            adapter.send_message_once(
                CHAT_ID, CONTENT, deadline=case["deadline"]
            ).message.message_id
            == MESSAGE_ID
        )
        assert observed == [
            ("GET", "/api/v1/auth/csrf-cookie"),
            ("POST", "/api/v1/auth/login"),
            ("POST", "/api/v1/chats"),
            ("POST", f"/api/v1/chats/{CHAT_ID}/messages"),
        ]
    finally:
        adapter.close_clients(deadline=case["deadline"])
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_slow_trickling_headers_cannot_outlive_absolute_http_deadline(
    setup_case,
) -> None:
    case = setup_case
    observed: list[tuple[str, str]] = []
    started = threading.Event()
    stop = threading.Event()
    server, thread = _local_server(
        _local_http_handler(observed, trickle_started=started, stop_trickle=stop)
    )
    original_owner = case["owner"]
    owner = original_owner.__class__(
        **{
            **original_owner.__dict__,
            "published_ports": (("CADDY_HTTP", server.server_port),),
        }
    )
    case["reader"].owner = owner
    http_deadline = Deadline.after(0.35, clock=time.monotonic)
    adapter = http_adapter.OwnedNatsHttpPort(case["reader"], case["adapter"]._pins)
    began = time.monotonic()
    try:
        with pytest.raises(http_adapter.HttpObservationNotReady):
            adapter.login_admin(owner, ADMIN_ID, deadline=http_deadline)
        elapsed = time.monotonic() - began
        assert started.is_set()
        assert elapsed < 0.8
        assert observed == [("GET", "/api/v1/auth/csrf-cookie")]
    finally:
        stop.set()
        adapter.close_clients(deadline=case["deadline"])
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
