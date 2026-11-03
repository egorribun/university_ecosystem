"""Worker assembly contracts; no Gunicorn process or SPIRE agent is started."""

from unittest.mock import AsyncMock, Mock

import pytest

from app.server import spiffe_worker
from app.server.spiffe_worker import BackendWorker
from tests.test_internal_http_mtls import environment


@pytest.mark.asyncio
@pytest.mark.parametrize("started", [True, False])
async def test_worker_binds_guarded_protocols_after_config_load(
    monkeypatch: pytest.MonkeyPatch,
    started: bool,
) -> None:
    for key, value in environment().items():
        monkeypatch.setenv(key, value)
    worker = object.__new__(BackendWorker)
    worker.config = Mock()
    worker.wsgi = Mock()
    worker.sockets = []
    monkeypatch.setattr(worker, "_install_sigquit_handler", Mock())
    source = Mock()
    monkeypatch.setattr(
        spiffe_worker.WorkloadContexts, "connect", Mock(return_value=source)
    )
    guard = Mock()
    monkeypatch.setattr(spiffe_worker, "TransportGuard", Mock(return_value=guard))
    http_protocol, ws_protocol = type("HTTP", (), {}), type("WS", (), {})
    monkeypatch.setattr(
        spiffe_worker,
        "guarded_protocols",
        Mock(return_value=(http_protocol, ws_protocol)),
    )
    server = Mock(started=started)
    server.serve = AsyncMock()
    monkeypatch.setattr(spiffe_worker, "Server", Mock(return_value=server))
    if started:
        await worker._serve()
    else:
        with pytest.raises(SystemExit) as caught:
            await worker._serve()
        assert caught.value.code == spiffe_worker.Arbiter.WORKER_BOOT_ERROR
    assert worker.config.http is http_protocol
    assert worker.config.ws is ws_protocol
    assert worker.config.ssl is guard.start.return_value
    worker.config.load.assert_called_once()
    server.serve.assert_awaited_once_with(sockets=[])
    guard.close.assert_called_once()
    source.close.assert_called_once()


@pytest.mark.asyncio
async def test_worker_startup_error_closes_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in environment().items():
        monkeypatch.setenv(key, value)
    worker = object.__new__(BackendWorker)
    source = Mock()
    monkeypatch.setattr(
        spiffe_worker.WorkloadContexts, "connect", Mock(return_value=source)
    )
    guard = Mock()
    guard.start.side_effect = RuntimeError("initial context unavailable")
    monkeypatch.setattr(spiffe_worker, "TransportGuard", Mock(return_value=guard))
    with pytest.raises(RuntimeError, match="initial context unavailable"):
        await worker._serve()
    guard.close.assert_called_once()
    source.close.assert_called_once()


@pytest.mark.asyncio
async def test_disabled_worker_never_opens_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_HTTP_MTLS_ENABLED", "false")
    conventional = AsyncMock()
    monkeypatch.setattr(spiffe_worker.UvicornWorker, "_serve", conventional)
    source = Mock()
    monkeypatch.setattr(spiffe_worker.WorkloadContexts, "connect", source)
    await object.__new__(BackendWorker)._serve()
    conventional.assert_awaited_once()
    source.assert_not_called()


@pytest.mark.asyncio
async def test_guard_construction_failure_closes_connected_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in environment().items():
        monkeypatch.setenv(key, value)
    source = Mock()
    monkeypatch.setattr(
        spiffe_worker.WorkloadContexts, "connect", Mock(return_value=source)
    )
    failure = RuntimeError("cannot subscribe to workload updates")
    monkeypatch.setattr(spiffe_worker, "TransportGuard", Mock(side_effect=failure))
    server = Mock()
    monkeypatch.setattr(spiffe_worker, "Server", server)

    with pytest.raises(RuntimeError, match="cannot subscribe") as caught:
        await object.__new__(BackendWorker)._serve()

    assert caught.value is failure
    source.close.assert_called_once()
    server.assert_not_called()
