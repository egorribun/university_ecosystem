"""Behavioral controls for NATS error callback phase boundaries."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from typing import Any

import nats
import pytest
from nats.js.api import StreamConfig

import app.core.nats_broker as nats_broker_module
from app.core.nats_broker import NatsTaskBroker

ErrorCallback = Callable[[Exception], Awaitable[None]]


class _FakeJetStream:
    def __init__(self) -> None:
        self.added_streams: list[StreamConfig] = []

    async def add_stream(self, *, config: StreamConfig) -> None:
        self.added_streams.append(config)


class _FakeClient:
    def __init__(self, initial_error: Exception | None = None) -> None:
        self.initial_error = initial_error
        self.error_callback: ErrorCallback | None = None
        self.callback_errors: list[Exception] = []
        self.connect_options: dict[str, Any] = {}
        self.jetstream_context = _FakeJetStream()
        self.connected = False
        self.close_count = 0

    async def connect(
        self,
        servers: str,
        *,
        error_cb: ErrorCallback,
        **options: Any,
    ) -> None:
        assert servers == "nats://127.0.0.1:4222"
        self.error_callback = error_cb
        self.connect_options = options
        if self.initial_error is not None:
            self.callback_errors.append(self.initial_error)
            await error_cb(self.initial_error)
        self.connected = True

    def jetstream(self) -> _FakeJetStream:
        return self.jetstream_context

    async def close(self) -> None:
        self.close_count += 1
        self.connected = False


def _install_client(monkeypatch: pytest.MonkeyPatch, client: _FakeClient) -> None:
    monkeypatch.setattr(nats_broker_module, "NATS", lambda: client)
    monkeypatch.setattr(
        nats_broker_module.settings, "nats_url", "nats://127.0.0.1:4222"
    )
    monkeypatch.setattr(
        nats_broker_module.settings, "nats_auth_token", secrets.token_urlsafe(24)
    )


@pytest.mark.parametrize(
    "transient_error",
    [
        pytest.param(OSError("temporary socket outage"), id="socket-outage"),
        pytest.param(nats.errors.TimeoutError(), id="nats-timeout"),
    ],
)
async def test_transient_connect_callback_returns_and_allows_initialization(
    monkeypatch: pytest.MonkeyPatch, transient_error: Exception
) -> None:
    client = _FakeClient(initial_error=transient_error)
    _install_client(monkeypatch, client)
    broker = NatsTaskBroker()

    try:
        await broker.connect()
        assert client.callback_errors == [transient_error]
        assert client.connected is True
        assert broker._nc is client
        assert broker._js is client.jetstream_context
        assert len(client.jetstream_context.added_streams) == 6
        assert client.connect_options["max_reconnect_attempts"] == -1
        assert client.connect_options["connect_timeout"] == 2
    finally:
        await broker.close()

    assert client.close_count == 1


@pytest.mark.parametrize(
    "permanent_error",
    [
        pytest.param(
            nats.errors.Error("server rejected the initial protocol handshake"),
            id="server-protocol-error",
        ),
        pytest.param(nats.errors.AuthorizationError(), id="authorization-error"),
        pytest.param(
            nats.errors.InvalidUserCredentialsError("invalid credentials"),
            id="invalid-user-credentials",
        ),
    ],
)
async def test_permanent_callback_errors_propagate_during_initial_connect(
    monkeypatch: pytest.MonkeyPatch, permanent_error: Exception
) -> None:
    client = _FakeClient(initial_error=permanent_error)
    _install_client(monkeypatch, client)
    broker = NatsTaskBroker()

    try:
        with pytest.raises(type(permanent_error)):
            await broker.connect()
        assert client.callback_errors == [permanent_error]
        assert client.connected is False
        assert broker._nc is None
        assert broker._js is None
    finally:
        await broker.close()

    assert client.close_count == 1


async def test_error_callback_returns_after_initial_connect_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient()
    _install_client(monkeypatch, client)
    broker = NatsTaskBroker()

    try:
        await broker.connect()
        assert client.error_callback is not None
        assert broker._js is client.jetstream_context

        late_error = nats.errors.Error("late post-connect server event")
        callback_result = await client.error_callback(late_error)

        assert callback_result is None
        assert client.connected is True
        assert broker._nc is client
        assert broker._js is client.jetstream_context
    finally:
        await broker.close()

    assert client.close_count == 1


class _TimeoutScope:
    def __init__(self, proxy: _TimeoutProxy, kind: str, value: float) -> None:
        self.proxy = proxy
        self.kind = kind
        self.value = value

    async def __aenter__(self) -> None:
        scope = (self.kind, self.value)
        self.proxy.active_scopes.append(scope)
        self.proxy.events.append(("enter", *scope))

    async def __aexit__(self, *_exc_info: object) -> bool:
        assert self.proxy.active_scopes[-1] == (self.kind, self.value)
        self.proxy.active_scopes.pop()
        self.proxy.events.append(("exit", self.kind, self.value))
        if self.kind == "deadline" and not self.proxy.lock_wait_elapsed:
            # Model lock contention consuming three seconds of the shared budget.
            self.proxy.loop_time += 3.0
            self.proxy.lock_wait_elapsed = True
        return False


class _TimeoutProxy:
    """Isolate absolute deadline ordering from real clocks and asyncio state."""

    def __init__(self) -> None:
        self.active_scopes: list[tuple[str, float]] = []
        self.events: list[tuple[str, str, float]] = []
        self.deadlines: list[float] = []
        self.remaining_at_entry: list[float] = []
        self.loop_time = 1_000.0
        self.loop_time_reads = 0
        self.lock_wait_elapsed = False

    def __getattr__(self, name: str) -> Any:
        return getattr(asyncio, name)

    def get_running_loop(self) -> _TimeoutProxy:
        return self

    def time(self) -> float:
        self.loop_time_reads += 1
        return self.loop_time

    def timeout_at(self, when: float) -> _TimeoutScope:
        self.deadlines.append(when)
        self.remaining_at_entry.append(when - self.loop_time)
        return _TimeoutScope(self, "deadline", when)

    def timeout(self, seconds: float) -> _TimeoutScope:
        return _TimeoutScope(self, "duration", seconds)


class _LateInitializationFailure(RuntimeError):
    pass


class _LateFailJetStream(_FakeJetStream):
    async def add_stream(self, *, config: StreamConfig) -> None:
        await super().add_stream(config=config)
        if len(self.added_streams) == 6:
            raise _LateInitializationFailure(
                "stream provisioning failed after five successful streams"
            )


class _LateFailClient(_FakeClient):
    def __init__(self, timeout_proxy: _TimeoutProxy) -> None:
        super().__init__()
        self.timeout_proxy = timeout_proxy
        self.jetstream_context = _LateFailJetStream()
        self.initialization_deadline_active_when_closed: bool | None = None

    async def close(self) -> None:
        self.initialization_deadline_active_when_closed = any(
            kind == "deadline" for kind, _value in self.timeout_proxy.active_scopes
        )
        await super().close()


async def test_late_initialization_failure_cleans_up_after_timeout_scope_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeout_proxy = _TimeoutProxy()
    client = _LateFailClient(timeout_proxy)
    _install_client(monkeypatch, client)
    monkeypatch.setattr(nats_broker_module, "asyncio", timeout_proxy)
    broker = NatsTaskBroker()

    with pytest.raises(
        _LateInitializationFailure,
        match="stream provisioning failed after five successful streams",
    ):
        await broker.connect()

    assert len(client.jetstream_context.added_streams) == 6
    assert client.close_count == 1
    assert client.initialization_deadline_active_when_closed is False
    assert broker._nc is None
    assert broker._js is None
    assert not broker._connect_lock.locked()
    assert timeout_proxy.active_scopes == []
    assert timeout_proxy.loop_time_reads == 1
    assert timeout_proxy.deadlines == [1_005.0, 1_005.0]
    assert timeout_proxy.remaining_at_entry == [5.0, 2.0]
    assert timeout_proxy.events == [
        ("enter", "deadline", 1_005.0),
        ("exit", "deadline", 1_005.0),
        ("enter", "deadline", 1_005.0),
        ("exit", "deadline", 1_005.0),
        ("enter", "duration", 2.0),
        ("exit", "duration", 2.0),
    ]
