"""SDK configuration and probe transport contract (no SPIRE proof claimed)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives.serialization import Encoding

from app.server import internal_mtls as mtls
from app.server.internal_mtls import InternalHTTPMTLSConfigError
from tests.test_spiffe_identity import IDENTITY, NOW, leaf


def environment() -> dict[str, str]:
    return {
        mtls.ENABLED_ENV: "true",
        mtls.SERVER_ID_ENV: IDENTITY,
        mtls.CLIENT_IDS_ENV: IDENTITY + ",spiffe://university.ecosystem/worker",
        mtls.SOCKET_ENV: "unix:///spiffe-workload-api/agent.sock",
    }


@pytest.mark.parametrize("flag", ["", "0", "false", "no", "off"])
def test_disabled_does_not_require_an_agent(flag: str) -> None:
    assert mtls.load_internal_http_mtls({mtls.ENABLED_ENV: flag}) is None


@pytest.mark.parametrize("flag", ["1", "true", "yes", "on", " TRUE "])
def test_enabled_requires_exact_identities(flag: str) -> None:
    env = environment()
    env[mtls.ENABLED_ENV] = flag
    config = mtls.load_internal_http_mtls(env)
    assert config is not None
    assert config.server_identity == IDENTITY
    assert config.allowed_clients == frozenset(env[mtls.CLIENT_IDS_ENV].split(","))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        (mtls.ENABLED_ENV, "enabled"),
        (mtls.SOCKET_ENV, "tcp://agent:8081"),
        (mtls.SOCKET_ENV, "unix:relative"),
        (mtls.SOCKET_ENV, "unix:/bad\x00path"),
        (mtls.SERVER_ID_ENV, ""),
        (mtls.SERVER_ID_ENV, IDENTITY + "\n"),
        (mtls.CLIENT_IDS_ENV, IDENTITY + "\n"),
        (mtls.SERVER_ID_ENV, "spiffe://university.ecosystem"),
        (mtls.CLIENT_IDS_ENV, ""),
        (mtls.CLIENT_IDS_ENV, IDENTITY + ","),
        (mtls.CLIENT_IDS_ENV, IDENTITY + "," + IDENTITY),
        (mtls.CLIENT_IDS_ENV, "spiffe://university.ecosystem/other"),
        (mtls.CLIENT_IDS_ENV, IDENTITY + ",spiffe://other.domain/worker"),
        (mtls.CLIENT_IDS_ENV, IDENTITY + ",spiffe://university.ecosystem"),
        (mtls.CLIENT_IDS_ENV, IDENTITY + ",not-an-id"),
    ],
)
def test_invalid_configuration_fails_closed(key: str, value: str) -> None:
    env = environment()
    env[key] = value
    with pytest.raises(InternalHTTPMTLSConfigError):
        mtls.load_internal_http_mtls(env)


@pytest.mark.parametrize(
    ("path", "port"),
    [("/arbitrary", 8000), ("/health/ready", 0), ("/health/ready", 65536)],
)
def test_probe_target_is_fixed(path: str, port: int) -> None:
    with pytest.raises(InternalHTTPMTLSConfigError):
        mtls.probe(path, port, environment())


@pytest.mark.parametrize("valid_identity", [True, False])
def test_probe_validates_peer_before_http(
    monkeypatch: pytest.MonkeyPatch, valid_identity: bool
) -> None:
    source = Mock()
    connect_source = Mock(return_value=source)
    monkeypatch.setattr(mtls.WorkloadContexts, "connect", connect_source)
    connection = Mock()
    peer = IDENTITY if valid_identity else "spiffe://university.ecosystem/impostor"
    connection.sock.getpeercert.return_value = leaf((peer,)).public_bytes(Encoding.DER)
    connection.sock.get_verified_chain.return_value = [
        connection.sock.getpeercert.return_value
    ]
    connection.getresponse.return_value.status = 200
    events: list[str] = []
    connection.connect.side_effect = lambda: events.append("tls")
    connection.request.side_effect = lambda *_args: events.append("http")
    monkeypatch.setattr(
        mtls.http.client, "HTTPSConnection", Mock(return_value=connection)
    )
    clock = Mock()
    clock.now.return_value = NOW
    monkeypatch.setattr(mtls, "datetime", clock)
    assert mtls.probe("/health/ready", 8000, environment()) is valid_identity
    assert events == (["tls", "http"] if valid_identity else ["tls"])
    source.close.assert_called_once()
    connection.close.assert_called_once()
    connect_source.assert_called_once_with(
        environment()[mtls.SOCKET_ENV], IDENTITY, server=False, timeout=1.0
    )


def test_plaintext_probe_only_when_explicitly_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = Mock()
    connection.getresponse.return_value.status = 200
    monkeypatch.setattr(
        mtls.http.client, "HTTPConnection", Mock(return_value=connection)
    )
    assert mtls.probe("/health/ready", 8000, {})
    connection.close.assert_called_once()


@pytest.mark.parametrize("result", [True, False])
def test_probe_cli_status(monkeypatch: pytest.MonkeyPatch, result: bool) -> None:
    monkeypatch.setattr(mtls, "probe", Mock(return_value=result))
    assert mtls.main(["probe", "/health/ready"]) == (0 if result else 1)


def test_probe_cli_failure_does_not_print_material(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        mtls,
        "probe",
        Mock(side_effect=InternalHTTPMTLSConfigError("private diagnostic")),
    )
    assert mtls.main(["probe", "/health/ready"]) == 2
    assert "private diagnostic" not in capsys.readouterr().err


def test_actual_image_selects_transport_worker_and_shared_probe() -> None:
    dockerfile = Path("backend.Dockerfile").read_text()
    assert '"--worker-class", "app.server.spiffe_worker.BackendWorker"' in dockerfile
    assert '"-m", "app.server.internal_mtls", "probe", "/health/ready"' in dockerfile
    assert '"--worker-class", "uvicorn.workers.UvicornWorker"' not in dockerfile
