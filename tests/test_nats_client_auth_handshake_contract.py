"""Regression contract for initial NATS authentication rejection handling."""

from __future__ import annotations

import asyncio
import secrets
from typing import Any

import nats
import nats.aio.client as nats_client_module
import pytest
from nats.aio.client import Client

import app.core.nats_broker as nats_broker_module
from app.core.nats_broker import NatsTaskBroker

_INFO_LINE = (
    b'INFO {"server_id":"contract-test","version":"2.11.0",'
    b'"max_payload":1048576,"auth_required":true}\r\n'
)
_AUTHORIZATION_REJECTION = b"-ERR 'Authorization Violation'\r\n"


async def test_initial_auth_rejection_propagates_before_retry_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_errors: list[BaseException] = []
    connect_options: list[dict[str, Any]] = []
    transports: list[Any] = []
    clients: list[Client] = []
    retry_gate = asyncio.Event()

    class ControlledTransport:
        def __init__(self) -> None:
            self.read_count = 0
            self.writes: list[bytes] = []
            self.closed = False
            self.close_count = 0
            transports.append(self)

        async def connect(
            self, uri: Any, *, buffer_size: int, connect_timeout: int
        ) -> None:
            assert uri.hostname == "127.0.0.1"
            assert buffer_size > 0
            assert connect_timeout == 2
            if len(transports) > 1:
                await asyncio.wait_for(retry_gate.wait(), timeout=2)

        async def connect_tls(
            self,
            uri: Any,
            ssl_context: Any,
            buffer_size: int,
            connect_timeout: int,
        ) -> None:
            del uri, ssl_context, buffer_size, connect_timeout
            raise AssertionError("the test URL must use the controlled TCP transport")

        async def readline(self) -> bytes:
            self.read_count += 1
            if self.read_count == 1:
                return _INFO_LINE
            if self.read_count == 2:
                return _AUTHORIZATION_REJECTION
            await asyncio.wait_for(retry_gate.wait(), timeout=2)
            return b""

        async def read(self, buffer_size: int) -> bytes:
            del buffer_size
            await asyncio.wait_for(retry_gate.wait(), timeout=2)
            return b""

        def write(self, payload: bytes) -> None:
            self.writes.append(payload)

        def writelines(self, payload: list[bytes]) -> None:
            self.writes.extend(payload)

        async def drain(self) -> None:
            return None

        async def wait_closed(self) -> None:
            return None

        def close(self) -> None:
            self.close_count += 1
            self.closed = True

        def at_eof(self) -> bool:
            return self.closed

        def __bool__(self) -> bool:
            return not self.closed

    class ObservedClient(Client):
        def __init__(self) -> None:
            super().__init__()
            clients.append(self)

        async def connect(self, *args: Any, **kwargs: Any) -> None:
            original_error_cb = kwargs.get("error_cb")

            async def observe_error(error: BaseException) -> None:
                observed_errors.append(error)
                if original_error_cb is not None:
                    await original_error_cb(error)

            kwargs["error_cb"] = observe_error
            # This public timing option bounds retry observation without disabling reconnect.
            kwargs.setdefault("reconnect_time_wait", 0.01)
            connect_options.append(dict(kwargs))
            await super().connect(*args, **kwargs)

    monkeypatch.setattr(nats_client_module, "TcpTransport", ControlledTransport)
    monkeypatch.setattr(nats_broker_module, "NATS", ObservedClient)
    monkeypatch.setattr(nats, "NATS", ObservedClient)
    monkeypatch.setattr(
        nats_broker_module.settings, "nats_url", "nats://127.0.0.1:4222"
    )
    test_token = secrets.token_urlsafe(24)
    monkeypatch.setattr(nats_broker_module.settings, "nats_auth_token", test_token)

    broker = NatsTaskBroker()
    try:
        with pytest.raises(nats.errors.Error):
            await asyncio.wait_for(broker.connect(), timeout=0.5)

        assert len(observed_errors) == 1
        assert isinstance(observed_errors[0], nats.errors.Error)
        assert "Authorization Violation" in str(observed_errors[0])
        assert len(transports) == 1
        assert transports[0].close_count == 1
        assert b"PING\r\n" in transports[0].writes
        assert broker._nc is None
        assert broker._js is None
        assert len(clients) == 1
        assert len(connect_options) == 1
        assert connect_options[0]["connect_timeout"] == 2
        assert connect_options[0]["max_reconnect_attempts"] == -1
        assert connect_options[0].get("allow_reconnect", True) is True
    finally:
        retry_gate.set()
        await asyncio.wait_for(broker.close(), timeout=3)
        # These are in-memory test doubles; release any transport left open by
        # the deliberately failing retry-path implementation.
        for transport in transports:
            if not transport.closed:
                transport.close()
