"""AUD-373: mTLS contract for the backend listener and its exec health probe.

Certificates are minted in memory with ``cryptography`` so the tests exercise the
same ``ssl`` loading path as Gunicorn and the probe without shared fixtures.
"""

from __future__ import annotations

import datetime
import http.server
import runpy
import ssl
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app.server.internal_mtls import (
    CA_FILE_ENV,
    CERT_FILE_ENV,
    ENABLED_ENV,
    KEY_FILE_ENV,
    InternalHTTPMTLSConfigError,
    InternalHTTPMTLSMaterial,
    load_internal_http_mtls,
    main,
    probe,
)

BACKEND_SPIFFE_ID = "spiffe://university.ecosystem/ns/university-ecosystem/sa/app"
ROGUE_SPIFFE_ID = "spiffe://attacker.example/ns/evil/sa/rogue"


@dataclass(frozen=True)
class _Pair:
    cert: x509.Certificate
    key: ec.EllipticCurvePrivateKey


@dataclass(frozen=True)
class _Material:
    cert: Path
    key: Path
    ca: Path
    rogue_cert: Path
    rogue_key: Path


def _new_ca(common_name: str) -> _Pair:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return _Pair(cert=cert, key=key)


def _new_leaf(ca: _Pair, spiffe_id: str) -> _Pair:
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "workload")]))
        .issuer_name(ca.cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.UniformResourceIdentifier(spiffe_id)]),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage(
                [ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(ca.key, hashes.SHA256())
    )
    return _Pair(cert=cert, key=key)


def _write_pair(directory: Path, prefix: str, pair: _Pair) -> tuple[Path, Path]:
    cert_path = directory / f"{prefix}.crt"
    key_path = directory / f"{prefix}.key"
    cert_path.write_bytes(pair.cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        pair.key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


@pytest.fixture
def material(tmp_path: Path) -> _Material:
    ca = _new_ca("internal-test-ca")
    rogue_ca = _new_ca("rogue-test-ca")
    server = _new_leaf(ca, BACKEND_SPIFFE_ID)
    rogue = _new_leaf(rogue_ca, ROGUE_SPIFFE_ID)
    cert, key = _write_pair(tmp_path, "tls", server)
    ca_path = tmp_path / "ca.crt"
    ca_path.write_bytes(ca.cert.public_bytes(serialization.Encoding.PEM))
    rogue_cert, rogue_key = _write_pair(tmp_path, "rogue", rogue)
    return _Material(
        cert=cert,
        key=key,
        ca=ca_path,
        rogue_cert=rogue_cert,
        rogue_key=rogue_key,
    )


def _enabled_env(material: _Material, *, cert: Path | None = None) -> dict[str, str]:
    return {
        ENABLED_ENV: "true",
        CERT_FILE_ENV: str(cert or material.cert),
        KEY_FILE_ENV: str(material.key),
        CA_FILE_ENV: str(material.ca),
    }


@pytest.fixture(autouse=True)
def _clean_mtls_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (ENABLED_ENV, CERT_FILE_ENV, KEY_FILE_ENV, CA_FILE_ENV):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("flag", ["", "0", "false", "No", " OFF "])
def test_disabled_flag_returns_no_material(flag: str) -> None:
    assert load_internal_http_mtls({ENABLED_ENV: flag}) is None


def test_unset_flag_returns_no_material() -> None:
    assert load_internal_http_mtls({}) is None


@pytest.mark.parametrize("flag", ["tru", "enabled", "2", "yes please"])
def test_unknown_flag_value_fails_closed(flag: str) -> None:
    with pytest.raises(InternalHTTPMTLSConfigError, match=ENABLED_ENV):
        load_internal_http_mtls({ENABLED_ENV: flag})


@pytest.mark.parametrize("flag", ["1", "true", "YES", " on "])
def test_enabled_flag_spellings_load_valid_material(
    material: _Material, flag: str
) -> None:
    environ = _enabled_env(material)
    environ[ENABLED_ENV] = flag

    loaded = load_internal_http_mtls(environ)

    assert loaded == InternalHTTPMTLSMaterial(
        certfile=str(material.cert),
        keyfile=str(material.key),
        ca_certs=str(material.ca),
    )


@pytest.mark.parametrize("missing", [CERT_FILE_ENV, KEY_FILE_ENV, CA_FILE_ENV])
def test_enabled_without_material_path_fails_closed(
    material: _Material, missing: str
) -> None:
    environ = _enabled_env(material)
    del environ[missing]

    with pytest.raises(InternalHTTPMTLSConfigError, match=missing):
        load_internal_http_mtls(environ)


@pytest.mark.parametrize("missing", [CERT_FILE_ENV, KEY_FILE_ENV, CA_FILE_ENV])
def test_enabled_with_blank_material_path_fails_closed(
    material: _Material, missing: str
) -> None:
    environ = _enabled_env(material)
    environ[missing] = "   "

    with pytest.raises(InternalHTTPMTLSConfigError, match=missing):
        load_internal_http_mtls(environ)


def test_enabled_with_missing_file_fails_closed(
    material: _Material, tmp_path: Path
) -> None:
    environ = _enabled_env(material, cert=tmp_path / "absent.crt")

    with pytest.raises(InternalHTTPMTLSConfigError, match=CERT_FILE_ENV):
        load_internal_http_mtls(environ)


def test_enabled_with_directory_path_fails_closed(
    material: _Material, tmp_path: Path
) -> None:
    environ = _enabled_env(material, cert=tmp_path)

    with pytest.raises(InternalHTTPMTLSConfigError, match="readable file"):
        load_internal_http_mtls(environ)


def test_enabled_with_garbage_certificate_fails_closed(
    material: _Material, tmp_path: Path
) -> None:
    garbage = tmp_path / "garbage.crt"
    garbage.write_text("not a certificate\n", encoding="utf-8")

    with pytest.raises(InternalHTTPMTLSConfigError, match="invalid"):
        load_internal_http_mtls(_enabled_env(material, cert=garbage))


def test_enabled_with_mismatched_key_fails_closed(material: _Material) -> None:
    environ = _enabled_env(material)
    environ[KEY_FILE_ENV] = str(material.rogue_key)

    with pytest.raises(InternalHTTPMTLSConfigError, match="invalid"):
        load_internal_http_mtls(environ)


def test_enabled_with_garbage_ca_bundle_fails_closed(
    material: _Material, tmp_path: Path
) -> None:
    garbage_ca = tmp_path / "garbage-ca.crt"
    garbage_ca.write_text("not a bundle\n", encoding="utf-8")
    environ = _enabled_env(material)
    environ[CA_FILE_ENV] = str(garbage_ca)

    with pytest.raises(InternalHTTPMTLSConfigError, match="invalid"):
        load_internal_http_mtls(environ)


@contextmanager
def _mtls_health_server(
    material: _Material,
    *,
    status: HTTPStatus = HTTPStatus.OK,
) -> Iterator[int]:
    """Serve health checks that require a client chain to the internal CA."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(material.cert, material.key)
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(material.ca)

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(status.value)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            return

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(httpd.server_address[1])
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_probe_succeeds_with_pod_certificate_against_ready_listener(
    material: _Material,
) -> None:
    with _mtls_health_server(material) as port:
        assert probe("/health/ready", port, _enabled_env(material)) is True


def test_probe_reports_unhealthy_status_as_failure(material: _Material) -> None:
    with _mtls_health_server(material, status=HTTPStatus.SERVICE_UNAVAILABLE) as port:
        assert probe("/health/ready", port, _enabled_env(material)) is False


def test_probe_with_certificate_outside_internal_ca_is_rejected(
    material: _Material,
) -> None:
    rogue_env = _enabled_env(material, cert=material.rogue_cert)
    rogue_env[KEY_FILE_ENV] = str(material.rogue_key)

    with _mtls_health_server(material) as port:
        assert probe("/health/live", port, rogue_env) is False


def test_probe_reports_unreachable_listener_as_failure(material: _Material) -> None:
    with _mtls_health_server(material) as port:
        pass

    assert probe("/health/live", port, _enabled_env(material)) is False


def test_probe_requires_mtls_enabled(material: _Material) -> None:
    with pytest.raises(InternalHTTPMTLSConfigError, match=ENABLED_ENV):
        probe("/health/live", 8000, {})


def test_main_exit_code_reports_healthy_listener(
    material: _Material, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in _enabled_env(material).items():
        monkeypatch.setenv(name, value)

    with _mtls_health_server(material) as port:
        assert main(["probe", "/health/live", "--port", str(port)]) == 0


def test_main_exit_code_reports_unhealthy_listener(
    material: _Material, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in _enabled_env(material).items():
        monkeypatch.setenv(name, value)

    with _mtls_health_server(material, status=HTTPStatus.SERVICE_UNAVAILABLE) as port:
        assert main(["probe", "/health/ready", "--port", str(port)]) == 1


def test_main_reports_misconfiguration_without_secret_material(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["probe", "/health/live"]) == 2
    assert "internal mTLS probe misconfigured" in capsys.readouterr().err


def test_main_rejects_probe_paths_outside_health_contract() -> None:
    with pytest.raises(SystemExit):
        main(["probe", "/api/v1/admin/users"])


def test_module_entrypoint_runs_probe_and_exits(
    material: _Material, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in _enabled_env(material).items():
        monkeypatch.setenv(name, value)
    monkeypatch.delitem(sys.modules, "app.server.internal_mtls")
    with _mtls_health_server(material) as port:
        monkeypatch.setattr(
            sys, "argv", ["internal_mtls", "probe", "/health/live", "--port", str(port)]
        )
        with pytest.raises(SystemExit) as exit_info:
            runpy.run_module("app.server.internal_mtls", run_name="__main__")

    assert exit_info.value.code == 0


def test_gunicorn_config_is_plaintext_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    namespace = runpy.run_module("app.server.gunicorn_conf")

    assert "certfile" not in namespace
    assert "keyfile" not in namespace
    assert "cert_reqs" not in namespace
    monkeypatch.setenv(ENABLED_ENV, "false")
    assert "certfile" not in runpy.run_module("app.server.gunicorn_conf")


def test_gunicorn_config_requires_client_certificates_when_enabled(
    material: _Material, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in _enabled_env(material).items():
        monkeypatch.setenv(name, value)

    namespace = runpy.run_module("app.server.gunicorn_conf")

    assert namespace["certfile"] == str(material.cert)
    assert namespace["keyfile"] == str(material.key)
    assert namespace["ca_certs"] == str(material.ca)
    assert namespace["cert_reqs"] == int(ssl.CERT_REQUIRED) == 2


def test_gunicorn_config_import_fails_closed_on_missing_material(
    material: _Material, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in _enabled_env(material).items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(CA_FILE_ENV)

    with pytest.raises(InternalHTTPMTLSConfigError, match=CA_FILE_ENV):
        runpy.run_module("app.server.gunicorn_conf")
