from unittest.mock import ANY, MagicMock, call

import pytest
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from tests.integration.test_infrastructure import nats_server


@pytest.fixture
def configured_nats_container(monkeypatch):
    container = MagicMock()
    container.with_exposed_ports.return_value = container
    container.with_command.return_value = container
    container.waiting_for.return_value = container
    container.__enter__.return_value = container
    constructor = MagicMock(return_value=container)
    monkeypatch.setattr("testcontainers.core.container.DockerContainer", constructor)

    fixture = nats_server.__wrapped__()
    assert next(fixture) is container
    try:
        yield container
    finally:
        with pytest.raises(StopIteration):
            next(fixture)
        container.__exit__.assert_called_once_with(None, None, None)


def test_nats_fixture_waits_for_server_readiness_and_tears_down(
    configured_nats_container,
):
    container = configured_nats_container
    container.with_exposed_ports.assert_called_once_with(4222)
    container.with_command.assert_called_once_with("-js")
    container.waiting_for.assert_called_once()
    strategy = container.waiting_for.call_args.args[0]
    assert isinstance(strategy, LogMessageWaitStrategy)
    assert strategy._message.pattern == "Server is ready"
    assert strategy._startup_timeout == 5
    assert container.mock_calls.index(
        call.waiting_for(ANY)
    ) < container.mock_calls.index(call.__enter__())


def test_nats_readiness_waits_for_ready_log(configured_nats_container):
    strategy = configured_nats_container.waiting_for.call_args.args[0]
    target = MagicMock()
    target.get_wrapped_container.return_value.status = "running"
    target.get_logs.side_effect = [
        (b"", b"Starting JetStream"),
        (b"", b"Server is ready"),
    ]

    strategy.wait_until_ready(target)

    assert target.get_logs.call_count == 2


def test_nats_readiness_propagates_permission_error(configured_nats_container):
    strategy = configured_nats_container.waiting_for.call_args.args[0]
    target = MagicMock()
    target.get_logs.side_effect = PermissionError("denied")

    with pytest.raises(PermissionError, match="denied"):
        strategy.wait_until_ready(target)

    target.get_logs.assert_called_once_with()


def test_nats_readiness_has_a_bounded_failure(configured_nats_container):
    strategy = configured_nats_container.waiting_for.call_args.args[0]
    strategy.with_startup_timeout(0.01).with_poll_interval(0.001)
    target = MagicMock()
    target.get_logs.return_value = (b"", b"")
    target.get_wrapped_container.return_value.status = "running"
    target.get_wrapped_container.return_value.attrs = {"State": {"Status": "running"}}

    with pytest.raises(TimeoutError, match="Server is ready"):
        strategy.wait_until_ready(target)
