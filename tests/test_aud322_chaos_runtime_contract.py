"""Exercise the chaos HTTP and outbox boundaries without touching containers."""

from __future__ import annotations

import secrets
import time
import uuid
from collections.abc import Generator, Iterator
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import sqlalchemy as sa

from tests.chaos import test_resilience as resilience


def test_chaos_login_uses_rotating_csrf_and_cookie_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password = secrets.token_urlsafe(24)
    monkeypatch.setenv("CHAOS_TEST_USER", "synthetic-student")
    monkeypatch.setenv("CHAOS_TEST_PASSWORD", password)
    monkeypatch.setattr(resilience, "BASE_URL", "http://chaos.invalid")
    paths: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/v1/auth/csrf-cookie":
            return httpx.Response(
                200, headers={"set-cookie": "csrf_token=before; Path=/"}
            )
        if request.url.path == "/api/v1/auth/login":
            assert paths == ["/api/v1/auth/csrf-cookie", "/api/v1/auth/login"]
            assert request.headers["x-csrf-token"] == "before"
            assert "csrf_token=before" in request.headers["cookie"]
            return httpx.Response(
                200,
                json={"user": {"id": "synthetic"}},
                headers=[
                    ("set-cookie", "access_token_v2=session; Path=/; HttpOnly"),
                    ("set-cookie", "csrf_token=after; Path=/"),
                ],
            )
        assert request.url.path == "/api/v1/chats/room/messages"
        assert request.headers["x-csrf-token"] == "after"
        assert "access_token_v2=session" in request.headers["cookie"]
        assert "authorization" not in request.headers
        assert request.headers["content-type"].startswith("multipart/form-data;")
        assert b'name="content"' in request.content
        assert b"chaos-message" in request.content
        return httpx.Response(200, json={"id": str(uuid.uuid4())})

    real_client = httpx.Client

    def local_client(*args: object, **kwargs: object) -> httpx.Client:
        return real_client(*args, **kwargs, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(resilience.httpx, "Client", local_client)
    fixture: Generator[httpx.Client] = resilience.authenticated_client.__wrapped__(None)
    try:
        client = next(fixture)
        response = resilience._post_chaos_message(client, "room", "chaos-message")
        assert response.status_code == 200
    finally:
        fixture.close()
    assert paths == [
        "/api/v1/auth/csrf-cookie",
        "/api/v1/auth/login",
        "/api/v1/chats/room/messages",
    ]


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("csrf_status", "initialize the chaos CSRF"),
        ("csrf_missing", "did not provide a CSRF cookie"),
        ("login_status", "Could not authenticate"),
        ("session_missing", "authenticated session cookie"),
        ("rotation_missing", "did not rotate the CSRF cookie"),
    ],
)
def test_chaos_login_fails_closed_on_missing_preconditions(
    monkeypatch: pytest.MonkeyPatch, failure: str, message: str
) -> None:
    password = secrets.token_urlsafe(24)
    monkeypatch.setenv("CHAOS_TEST_PASSWORD", password)
    requests: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/api/v1/auth/csrf-cookie":
            if failure == "csrf_status":
                return httpx.Response(503)
            if failure == "csrf_missing":
                return httpx.Response(200)
            return httpx.Response(
                200, headers={"set-cookie": "csrf_token=before; Path=/"}
            )
        assert request.url.path == "/api/v1/auth/login"
        if failure == "login_status":
            return httpx.Response(401, text=password)
        headers = []
        if failure != "session_missing":
            headers.append(("set-cookie", "access_token_v2=session; Path=/; HttpOnly"))
        if failure != "rotation_missing":
            headers.append(("set-cookie", "csrf_token=after; Path=/"))
        return httpx.Response(200, headers=headers)

    real_client = httpx.Client

    def local_client(*args: object, **kwargs: object) -> httpx.Client:
        return real_client(*args, **kwargs, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(resilience.httpx, "Client", local_client)
    fixture: Generator[httpx.Client] = resilience.authenticated_client.__wrapped__(None)
    try:
        with pytest.raises(pytest.fail.Exception, match=message) as captured:
            next(fixture)
        assert password not in str(captured.value)
    finally:
        fixture.close()
    assert requests[0] == "/api/v1/auth/csrf-cookie"
    assert len(requests) == (1 if failure.startswith("csrf_") else 2)


@pytest.fixture
def event_database(tmp_path: Path) -> Iterator[tuple[str, sa.Engine]]:
    url = f"sqlite:///{(tmp_path / 'chaos-events.sqlite').as_posix()}"
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE stored_events "
                "(id TEXT PRIMARY KEY, event_type TEXT NOT NULL, "
                "aggregate_id TEXT NOT NULL, status TEXT NOT NULL, processed_at TEXT)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE failed_outbox_events (original_event_id TEXT NOT NULL)"
            )
        )
    yield url, engine
    engine.dispose()


def test_processed_outbox_probe_uses_the_exact_event_and_processed_timestamp(
    event_database: tuple[str, sa.Engine], monkeypatch: pytest.MonkeyPatch
) -> None:
    url, engine = event_database
    target, other = str(uuid.uuid4()), str(uuid.uuid4())
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO stored_events VALUES "
                "(:target, 'chat.message_sent', 'target-message', 'pending', NULL), "
                "(:other, 'chat.message_sent', 'other-message', 'processed', 'done')"
            ),
            {"target": target, "other": other},
        )
    monkeypatch.setattr(resilience, "_OUTBOX_POLL_INTERVAL_SECONDS", 0.001)
    assert not resilience._wait_for_outbox_event_processed(url, target, timeout=0.01)
    with engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE stored_events SET processed_at = 'done' WHERE id = :id"),
            {"id": target},
        )
    assert resilience._wait_for_outbox_event_processed(url, target, timeout=0.1)


def test_processed_outbox_probe_rejects_a_dead_lettered_event(
    event_database: tuple[str, sa.Engine],
) -> None:
    url, engine = event_database
    event_id = str(uuid.uuid4())
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO stored_events VALUES "
                "(:id, 'chat.message_sent', 'target-message', 'pending', 'done')"
            ),
            {"id": event_id},
        )
        connection.execute(
            sa.text("INSERT INTO failed_outbox_events VALUES (:id)"), {"id": event_id}
        )
    with pytest.raises(AssertionError, match="dead-lettered"):
        resilience._wait_for_outbox_event_processed(url, event_id, timeout=0.1)


@pytest.mark.parametrize("condition", ["duplicate", "processed"])
def test_pending_outbox_probe_rejects_ambiguous_or_processed_rows(
    event_database: tuple[str, sa.Engine], condition: str
) -> None:
    url, engine = event_database
    message_id = str(uuid.uuid4())
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO stored_events VALUES "
                "(:id, 'chat.message_sent', :message, 'pending', :processed_at)"
            ),
            {
                "id": str(uuid.uuid4()),
                "message": message_id,
                "processed_at": "done" if condition == "processed" else None,
            },
        )
        if condition == "duplicate":
            connection.execute(
                sa.text(
                    "INSERT INTO stored_events VALUES "
                    "(:id, 'chat.message_sent', :message, 'pending', NULL)"
                ),
                {"id": str(uuid.uuid4()), "message": message_id},
            )
    with pytest.raises(AssertionError, match="outbox"):
        resilience._pending_message_event_id(url, message_id)


@pytest.mark.parametrize(
    ("url", "expected_driver"),
    [
        ("postgresql://localhost/example", "postgresql+psycopg"),
        ("postgresql+psycopg://localhost/example", "postgresql+psycopg"),
        ("sqlite://", "sqlite"),
    ],
)
def test_outbox_engine_uses_installed_sync_driver(
    monkeypatch: pytest.MonkeyPatch, url: str, expected_driver: str
) -> None:
    captured: list[sa.URL] = []
    sentinel = object()

    def create_engine(database_url: sa.URL, **kwargs: object) -> object:
        captured.append(database_url)
        assert kwargs == {"future": True}
        return sentinel

    monkeypatch.setattr(sa, "create_engine", create_engine)
    assert resilience._outbox_engine(url) is sentinel
    assert captured[0].drivername == expected_driver


@pytest.mark.parametrize("matching_event", [True, False])
def test_nats_outage_checks_only_the_sent_message_event(
    event_database: tuple[str, sa.Engine],
    monkeypatch: pytest.MonkeyPatch,
    matching_event: bool,
) -> None:
    url, engine = event_database
    message_id, target_event, unrelated_event = (str(uuid.uuid4()) for _ in range(3))
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO stored_events VALUES (:id, 'chat.message_sent', 'unrelated', 'pending', NULL)"
            ),
            {"id": unrelated_event},
        )
        if matching_event:
            connection.execute(
                sa.text(
                    "INSERT INTO stored_events VALUES (:id, 'chat.message_sent', :message, 'pending', NULL)"
                ),
                {"id": target_event, "message": message_id},
            )
    monkeypatch.setenv("DATABASE_URL_SYNC", url)
    monkeypatch.setattr(
        resilience,
        "time",
        SimpleNamespace(monotonic=time.monotonic, sleep=lambda _: None),
    )
    commands: list[str] = []

    def compose(command: str) -> str:
        commands.append(command)
        if command == "start nats":
            with engine.begin() as connection:
                connection.execute(
                    sa.text(
                        "UPDATE stored_events SET processed_at = 'done' WHERE id = :id"
                    ),
                    {"id": target_event},
                )
        return ""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"items": [{"id": "room"}]})
        assert request.headers["x-csrf-token"] == "signed-csrf"
        assert request.headers["content-type"].startswith("multipart/form-data;")
        assert b'name="content"' in request.content
        return httpx.Response(200, json={"id": message_id})

    monkeypatch.setattr(resilience, "_run_docker_compose", compose)
    with httpx.Client(
        base_url="http://chaos.invalid", transport=httpx.MockTransport(handle)
    ) as client:
        client.cookies.set("csrf_token", "signed-csrf")
        client.cookies.set("access_token_v2", "session")
        if matching_event:
            resilience.test_nats_outage_outbox_durability(None, client)
        else:
            with pytest.raises(AssertionError, match="outbox"):
                resilience.test_nats_outage_outbox_durability(None, client)
    assert commands == ["stop nats", "start nats"]


def test_valkey_requests_keep_one_fresh_key_and_use_cookie_csrf_and_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resilience, "time", SimpleNamespace(sleep=lambda _: None))
    monkeypatch.setenv("DATABASE_URL_SYNC", "sqlite://")
    commands: list[str] = []
    requests: list[str] = []
    probes: list[tuple[list[str], tuple[str, ...]]] = []
    response_id = str(uuid.uuid4())

    def compose(command: str) -> str:
        commands.append(command)
        return ""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"items": [{"id": "room"}]})
        requests.append(request.headers["idempotency-key"])
        assert request.headers["x-csrf-token"] == "signed-csrf"
        assert "access_token_v2=session" in request.headers["cookie"]
        assert request.headers["content-type"].startswith("multipart/form-data;")
        assert b'name="content"' in request.content
        return httpx.Response(200, json={"id": response_id})

    monkeypatch.setattr(resilience, "_run_docker_compose", compose)
    monkeypatch.setattr(
        resilience,
        "_assert_chat_send_db_state",
        lambda *args: probes.append((commands.copy(), args)),
    )
    with httpx.Client(
        base_url="http://chaos.invalid", transport=httpx.MockTransport(handle)
    ) as client:
        client.cookies.set("csrf_token", "signed-csrf")
        client.cookies.set("access_token_v2", "session")
        resilience.test_valkey_outage_idempotency_fail_open(None, client)
        resilience.test_valkey_outage_idempotency_fail_open(None, client)
    assert len(set(requests[:3])) == len(set(requests[3:])) == 1
    assert requests[0] != requests[3]
    assert commands == ["stop valkey", "start valkey"] * 2
    assert [state for state, _ in probes] == [
        commands[:1],
        commands[:2],
        commands[:3],
        commands[:4],
    ]
    assert all(probe[-1] == response_id for _, probe in probes)
    assert [probe[2] for _, probe in probes] == [
        requests[0],
        requests[0],
        requests[3],
        requests[3],
    ]


def test_valkey_resilience_does_not_hide_a_gateway_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resilience, "GATEWAY_URL", "http://chaos.invalid")
    monkeypatch.setattr(resilience, "time", SimpleNamespace(sleep=lambda _: None))
    commands: list[str] = []
    monkeypatch.setattr(resilience, "_run_docker_compose", commands.append)

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200)
        raise httpx.ConnectError("gateway disconnected", request=request)

    real_client = httpx.Client

    def local_client(*args: object, **kwargs: object) -> httpx.Client:
        return real_client(*args, **kwargs, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(resilience.httpx, "Client", local_client)
    with pytest.raises(httpx.ConnectError, match="gateway disconnected"):
        resilience.test_valkey_redis_down_resilience(None)

    assert commands == ["stop valkey", "start valkey"]


def test_valkey_resilience_accepts_a_gateway_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resilience, "GATEWAY_URL", "http://chaos.invalid")
    monkeypatch.setattr(resilience, "time", SimpleNamespace(sleep=lambda _: None))
    commands: list[str] = []
    monkeypatch.setattr(resilience, "_run_docker_compose", commands.append)

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200)
        raise httpx.ReadTimeout("rate limit probe timed out", request=request)

    real_client = httpx.Client

    def local_client(*args: object, **kwargs: object) -> httpx.Client:
        return real_client(*args, **kwargs, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(resilience.httpx, "Client", local_client)
    resilience.test_valkey_redis_down_resilience(None)

    assert commands == ["stop valkey", "start valkey"]


@pytest.mark.parametrize("status_code", [404, 503])
def test_ws_hub_proxy_fallback_rejects_non_gateway_error_status(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    monkeypatch.setattr(resilience, "GATEWAY_URL", "http://chaos.invalid")
    monkeypatch.setattr(resilience, "time", SimpleNamespace(sleep=lambda _: None))
    commands: list[str] = []
    monkeypatch.setattr(resilience, "_run_docker_compose", commands.append)

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200)
        assert request.url.path == "/ws/chat"
        return httpx.Response(status_code)

    real_client = httpx.Client

    def local_client(*args: object, **kwargs: object) -> httpx.Client:
        return real_client(*args, **kwargs, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(resilience.httpx, "Client", local_client)
    with pytest.raises(AssertionError, match="Expected 502"):
        resilience.test_ws_hub_down_gateway_proxy_fallback(None)

    assert commands == ["stop ws-hub", "start ws-hub"]
