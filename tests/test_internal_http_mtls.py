"""SDK configuration and probe transport contract (no SPIRE proof claimed)."""

from __future__ import annotations

import runpy
import ssl
import sys
from pathlib import Path
from typing import Any
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


@pytest.mark.parametrize(
    ("failure", "step", "error", "detail"),
    [
        (
            "connect",
            "workload_api_connect",
            OSError("connection refused"),
            "error=OSError: connection refused",
        ),
        (
            "current",
            "workload_api_current",
            mtls.WorkloadIdentityError("local workload trust bundle is missing"),
            "error=WorkloadIdentityError: local workload trust bundle is missing",
        ),
    ],
)
def test_workload_api_cli_failure_names_the_failing_step(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
    step: str,
    error: Exception,
    detail: str,
) -> None:
    source = Mock()
    connect_source = Mock(return_value=source)
    if failure == "connect":
        connect_source.side_effect = error
    else:
        source.current.side_effect = error
    monkeypatch.setattr(mtls.WorkloadContexts, "connect", connect_source)
    for key, value in environment().items():
        monkeypatch.setenv(key, value)

    assert mtls.main(["probe", "/health/ready"]) == 1
    assert (
        capsys.readouterr().err == f"internal_mtls_probe_failed step={step} {detail}\n"
    )
    connect_source.assert_called_once_with(
        environment()[mtls.SOCKET_ENV], IDENTITY, server=False, timeout=1.0
    )
    if failure == "current":
        source.close.assert_called_once()
    else:
        source.close.assert_not_called()


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


@pytest.mark.parametrize(
    "error",
    [OSError("unavailable"), mtls.http.client.HTTPException("invalid response")],
)
def test_plaintext_probe_failure_closes_connection(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    connection = Mock()
    connection.request.side_effect = error
    monkeypatch.setattr(
        mtls.http.client, "HTTPConnection", Mock(return_value=connection)
    )
    assert not mtls.probe("/health/ready", 8000, {})
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "failure", ["no_socket", "no_leaf", "no_chain", "mismatched_chain"]
)
def test_secure_probe_incomplete_peer_proof_never_sends_http(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    source = Mock()
    monkeypatch.setattr(mtls.WorkloadContexts, "connect", Mock(return_value=source))
    connection = Mock()
    der = leaf((IDENTITY,)).public_bytes(Encoding.DER)
    connection.sock.getpeercert.return_value = der
    connection.sock.get_verified_chain.return_value = [der]
    if failure == "no_socket":
        connection.sock = None
    elif failure == "no_leaf":
        connection.sock.getpeercert.return_value = None
    elif failure == "no_chain":
        connection.sock.get_verified_chain.return_value = []
    else:
        connection.sock.get_verified_chain.return_value = [b"different leaf"]
    monkeypatch.setattr(
        mtls.http.client, "HTTPSConnection", Mock(return_value=connection)
    )
    assert not mtls.probe("/health/ready", 8000, environment())
    connection.request.assert_not_called()
    connection.close.assert_called_once()
    source.close.assert_called_once()


def test_module_entrypoint_exits_with_probe_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = Mock()
    connection.getresponse.return_value.status = 200
    monkeypatch.setattr(
        mtls.http.client, "HTTPConnection", Mock(return_value=connection)
    )
    monkeypatch.setenv(mtls.ENABLED_ENV, "false")
    monkeypatch.setattr(sys, "argv", ["internal_mtls", "probe", "/health/ready"])
    monkeypatch.delitem(sys.modules, "app.server.internal_mtls")
    with pytest.raises(SystemExit) as caught:
        runpy.run_module("app.server.internal_mtls", run_name="__main__")
    assert caught.value.code == 0
    connection.request.assert_called_once_with("GET", "/health/ready")
    connection.close.assert_called_once()


@pytest.mark.parametrize("result", [True, False])
def test_probe_cli_status(monkeypatch: pytest.MonkeyPatch, result: bool) -> None:
    monkeypatch.setattr(mtls, "probe", Mock(return_value=result))
    assert mtls.main(["probe", "/health/ready"]) == (0 if result else 1)


def test_probe_cli_failure_redacts_material(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    token = "A" * 48
    standard = "Ab/c+Ab" * 6 + "=="
    urlsafe = "Ab_c-Ab" * 6 + "=="
    safe_detail = "error=Connection refused"
    secret = "-----BEGIN PRIVATE KEY-----\nMIIBVQIBADANBgkq\n-----END PRIVATE KEY-----"
    monkeypatch.setattr(
        mtls,
        "probe",
        Mock(
            side_effect=InternalHTTPMTLSConfigError(
                f"bad {secret} {token} {standard} {urlsafe} {safe_detail}"
            ),
        ),
    )
    assert mtls.main(["probe", "/health/ready"]) == 2
    err = capsys.readouterr().err
    assert err == (
        "internal_mtls_probe_unavailable "
        "error=InternalHTTPMTLSConfigError: bad [redacted-pem] [redacted] "
        "[redacted] [redacted] error=Connection refused\n"
    )


def test_sanitizer_bounds_and_redacts_diagnostics() -> None:
    assert len(mtls._sanitize("word " * 100)) == 200
    assert mtls._sanitize("x" * 500) == "[redacted]"
    assert mtls._sanitize("line one\nline\ttwo") == "line one line two"
    assert mtls._sanitize(
        "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----"
    ) == ("[redacted-pem]")


def _secure_connection(
    monkeypatch: pytest.MonkeyPatch,
    *,
    peer: str = IDENTITY,
    connect_error: Exception | None = None,
    status: int = 200,
) -> Mock:
    monkeypatch.setattr(mtls.WorkloadContexts, "connect", Mock(return_value=Mock()))
    connection = Mock()
    der = leaf((peer,)).public_bytes(Encoding.DER)
    connection.sock.getpeercert.return_value = der
    connection.sock.get_verified_chain.return_value = [der]
    connection.getresponse.return_value.status = status
    if connect_error is not None:
        connection.connect.side_effect = connect_error
    monkeypatch.setattr(
        mtls.http.client, "HTTPSConnection", Mock(return_value=connection)
    )
    clock = Mock()
    clock.now.return_value = NOW
    monkeypatch.setattr(mtls, "datetime", clock)
    return connection


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            {
                "connect_error": ssl.SSLCertVerificationError(
                    1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"
                )
            },
            "internal_mtls_probe_failed step=tls_connect error=SSLCertVerificationError: "
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed\n",
        ),
        (
            {"peer": "spiffe://university.ecosystem/impostor"},
            "internal_mtls_probe_failed step=certificate_policy "
            "error=WorkloadIdentityError: peer workload identity is not authorized\n",
        ),
        (
            {"status": 503},
            "internal_mtls_probe_failed step=http_response status=503\n",
        ),
    ],
)
def test_secure_probe_failure_names_step_and_exception(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    kwargs: dict[str, Any],
    expected: str,
) -> None:
    connection = _secure_connection(monkeypatch, **kwargs)
    assert not mtls.probe("/health/ready", 8000, environment())
    assert capsys.readouterr().err == expected
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("sock", None, "step=peer_certificate error=TLSSocketMissing"),
        ("der", None, "step=peer_certificate error=PeerCertificateMissing"),
        ("chain", [b"other"], "step=verified_chain error=VerifiedChainMismatch"),
    ],
)
def test_secure_probe_incomplete_proof_names_step(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: object,
    expected: str,
) -> None:
    connection = _secure_connection(monkeypatch)
    if field == "sock":
        connection.sock = None
    elif field == "der":
        connection.sock.getpeercert.return_value = None
    else:
        connection.sock.get_verified_chain.return_value = value
    assert not mtls.probe("/health/ready", 8000, environment())
    assert expected in capsys.readouterr().err
    connection.request.assert_not_called()


def test_plaintext_probe_failure_names_step(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    connection = Mock()
    connection.request.side_effect = OSError("connection refused")
    monkeypatch.setattr(
        mtls.http.client, "HTTPConnection", Mock(return_value=connection)
    )
    assert not mtls.probe("/health/ready", 8000, {})
    assert capsys.readouterr().err == (
        "internal_mtls_probe_failed step=plain_http_request "
        "error=OSError: connection refused\n"
    )


def test_successful_probe_writes_no_diagnostics(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _secure_connection(monkeypatch)
    assert mtls.probe("/health/ready", 8000, environment())
    assert capsys.readouterr().err == ""


def test_actual_image_selects_transport_worker_and_shared_probe() -> None:
    dockerfile = Path("backend.Dockerfile").read_text()
    assert '"--worker-class", "app.server.spiffe_worker.BackendWorker"' in dockerfile
    assert '"-m", "app.server.internal_mtls", "probe", "/health/ready"' in dockerfile
    assert '"--worker-class", "uvicorn.workers.UvicornWorker"' not in dockerfile
