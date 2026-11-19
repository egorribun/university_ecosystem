"""Require an owned NATS container to be ready before exercising its clients."""

from __future__ import annotations

import inspect

import pytest
from testcontainers.core import container, wait_strategies

from tests.integration.test_infrastructure import nats_server


@pytest.mark.parametrize("readiness_fails", [False, True])
def test_nats_fixture_waits_before_yield_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch, readiness_fails: bool
) -> None:
    events: list[str] = []
    failure = TimeoutError("readiness unavailable")

    class FakeContainer:
        def __init__(self, image: str) -> None:
            assert image.startswith("nats:") and "@sha256:" in image

        def with_exposed_ports(self, *ports: int) -> FakeContainer:
            assert ports == (4222,)
            return self

        def with_command(self, command: str) -> FakeContainer:
            assert command == "-js"
            return self

        def __enter__(self) -> FakeContainer:
            events.append("entered")
            return self

        def __exit__(self, *_args: object) -> None:
            events.append("closed")

    class FakeWaitStrategy:
        def __init__(self, message: str) -> None:
            assert message == "Server is ready"
            self.timeout: int | None = None

        def with_startup_timeout(self, timeout: int) -> FakeWaitStrategy:
            assert timeout == 10
            self.timeout = timeout
            return self

        def wait_until_ready(self, target: object) -> None:
            assert self.timeout == 10
            assert isinstance(target, FakeContainer)
            events.append("ready")
            if readiness_fails:
                raise failure

    monkeypatch.setattr(container, "DockerContainer", FakeContainer)
    monkeypatch.setattr(wait_strategies, "LogMessageWaitStrategy", FakeWaitStrategy)
    fixture = inspect.unwrap(nats_server)()
    try:
        if readiness_fails:
            with pytest.raises(TimeoutError) as caught:
                next(fixture)
            assert caught.value is failure
            assert events == ["entered", "ready", "closed"]
        else:
            assert isinstance(next(fixture), FakeContainer)
            assert events == ["entered", "ready"]
    finally:
        fixture.close()
    assert events == ["entered", "ready", "closed"]
