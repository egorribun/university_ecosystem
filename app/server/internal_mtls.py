"""Mutual TLS for internal HTTP hops into the backend (AUD-373).

When ``INTERNAL_HTTP_MTLS_ENABLED`` is true, the backend Gunicorn worker serves
TLS and requires a client certificate that chains to the internal trust bundle.
Certificate material is read from mounted files when the worker starts, which
matches the gRPC mTLS contract in ``charts/university-ecosystem``: rotation
needs CA overlap and a controlled rollout restart.

The module is stdlib-only and reads its own environment on purpose. The
Gunicorn configuration and the exec readiness probe run outside the application
settings lifecycle, so they must not import application settings.
"""

from __future__ import annotations

import argparse
import http.client
import os
import ssl
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from typing import Final

ENABLED_ENV: Final = "INTERNAL_HTTP_MTLS_ENABLED"
CERT_FILE_ENV: Final = "INTERNAL_HTTP_MTLS_CERT_FILE"
KEY_FILE_ENV: Final = "INTERNAL_HTTP_MTLS_KEY_FILE"
CA_FILE_ENV: Final = "INTERNAL_HTTP_MTLS_CA_FILE"

PROBE_PATHS: Final = ("/health/live", "/health/ready")
PROBE_HOST: Final = "127.0.0.1"
PROBE_TIMEOUT_SECONDS: Final = 4

_DISABLED_VALUES: Final = frozenset({"", "0", "false", "no", "off"})
_ENABLED_VALUES: Final = frozenset({"1", "true", "yes", "on"})


class InternalHTTPMTLSConfigError(RuntimeError):
    """Raised when mTLS is requested but cannot be honored.

    The listener must never fall back to plaintext after the flag is set, so
    every failure in this module is raised rather than logged and ignored.
    """


@dataclass(frozen=True, slots=True)
class InternalHTTPMTLSMaterial:
    """Validated file paths for the backend server certificate and trust bundle."""

    certfile: str
    keyfile: str
    ca_certs: str


def load_internal_http_mtls(
    environ: Mapping[str, str],
) -> InternalHTTPMTLSMaterial | None:
    """Return validated TLS material when enabled, or ``None`` when disabled.

    Unknown flag values fail closed so a typo can never silently downgrade the
    listener to plaintext.
    """
    flag = environ.get(ENABLED_ENV, "").strip().lower()
    if flag in _DISABLED_VALUES:
        return None
    if flag not in _ENABLED_VALUES:
        raise InternalHTTPMTLSConfigError(f"{ENABLED_ENV} must be 'true' or 'false'")

    certfile = _required_file(environ, CERT_FILE_ENV)
    keyfile = _required_file(environ, KEY_FILE_ENV)
    ca_certs = _required_file(environ, CA_FILE_ENV)
    _validate_material(certfile=certfile, keyfile=keyfile, ca_certs=ca_certs)
    return InternalHTTPMTLSMaterial(
        certfile=certfile, keyfile=keyfile, ca_certs=ca_certs
    )


def _required_file(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise InternalHTTPMTLSConfigError(
            f"{name} is required when {ENABLED_ENV} is true"
        )
    if not os.path.isfile(value) or not os.access(value, os.R_OK):
        raise InternalHTTPMTLSConfigError(f"{name} must reference a readable file")
    return value


def _validate_material(*, certfile: str, keyfile: str, ca_certs: str) -> None:
    """Load the material exactly as the listener will, failing on any mismatch."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.verify_mode = ssl.CERT_REQUIRED
    try:
        context.load_cert_chain(certfile, keyfile)
        context.load_verify_locations(ca_certs)
    except (OSError, ssl.SSLError) as err:  # RZ-20-04: narrowed TLS material domain
        raise InternalHTTPMTLSConfigError(
            "internal mTLS certificate, key or CA material is invalid"
        ) from err


def probe(path: str, port: int, environ: Mapping[str, str]) -> bool:
    """Return whether a health endpoint answers 200 over the mTLS listener.

    The kubelet cannot present a client certificate, so the probe runs inside
    the pod and presents the pod's own certificate. The server accepts any chain
    to the internal CA, and the probe checks the chain without hostname matching
    because it targets loopback and SPIFFE IDs are URIs, not DNS names.
    """
    material = load_internal_http_mtls(environ)
    if material is None:
        raise InternalHTTPMTLSConfigError(f"probe requires {ENABLED_ENV}=true")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(material.ca_certs)
    context.load_cert_chain(material.certfile, material.keyfile)

    connection = http.client.HTTPSConnection(
        PROBE_HOST, port, timeout=PROBE_TIMEOUT_SECONDS, context=context
    )
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status == HTTPStatus.OK
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.server.internal_mtls")
    commands = parser.add_subparsers(dest="command", required=True)
    probe_parser = commands.add_parser(
        "probe", help="check a health endpoint over mTLS"
    )
    probe_parser.add_argument("path", choices=PROBE_PATHS)
    probe_parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    try:
        healthy = probe(args.path, args.port, os.environ)
    except InternalHTTPMTLSConfigError as err:
        sys.stderr.write(f"internal mTLS probe misconfigured: {err}\n")
        return 2
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
