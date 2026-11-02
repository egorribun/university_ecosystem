"""Strict SPIFFE transport configuration and exact-identity health probe."""

from __future__ import annotations

import argparse
import http.client
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Final

from cryptography import x509
from spiffe.errors import ArgumentError
from spiffe.workloadapi.errors import X509SourceError

from app.server.spiffe_identity import (
    WorkloadContexts,
    WorkloadIdentityError,
    authorize_verified_leaf,
    chain_deadline,
    validate_workload_id,
)

ENABLED_ENV: Final = "INTERNAL_HTTP_MTLS_ENABLED"
SERVER_ID_ENV: Final = "INTERNAL_HTTP_MTLS_SERVER_SPIFFE_ID"
CLIENT_IDS_ENV: Final = "INTERNAL_HTTP_MTLS_ALLOWED_CLIENT_SPIFFE_IDS"
SOCKET_ENV: Final = "SPIFFE_ENDPOINT_SOCKET"
PROBE_PATHS: Final = ("/health/live", "/health/ready")
PROBE_HOST: Final = "127.0.0.1"
_DISABLED_VALUES: Final = frozenset({"", "0", "false", "no", "off"})
_ENABLED_VALUES: Final = frozenset({"1", "true", "yes", "on"})


class InternalHTTPMTLSConfigError(WorkloadIdentityError):
    """Configuration cannot honor the requested secure transport."""


@dataclass(frozen=True, slots=True)
class InternalHTTPMTLSConfig:
    socket_path: str
    server_identity: str
    allowed_clients: frozenset[str]


def load_internal_http_mtls(
    environ: Mapping[str, str],
) -> InternalHTTPMTLSConfig | None:
    flag = environ.get(ENABLED_ENV, "").strip().lower()
    if flag in _DISABLED_VALUES:
        return None
    if flag not in _ENABLED_VALUES:
        raise InternalHTTPMTLSConfigError(f"{ENABLED_ENV} must be 'true' or 'false'")
    identity = environ.get(SERVER_ID_ENV, "")
    raw_clients = environ.get(CLIENT_IDS_ENV, "")
    if any(
        ord(character) < 32 or ord(character) == 127
        for character in identity + raw_clients
    ):
        raise InternalHTTPMTLSConfigError("identity configuration contains controls")
    identity = identity.strip()
    clients = raw_clients.split(",")
    clients = [client.strip() for client in clients]
    socket = environ.get(SOCKET_ENV, "").strip()
    if not socket.startswith("unix:/") or "\x00" in socket:
        raise InternalHTTPMTLSConfigError(
            "an absolute Unix Workload API endpoint is required"
        )
    if not all(clients) or len(set(clients)) != len(clients):
        raise InternalHTTPMTLSConfigError(
            "client identities must be nonempty and unique"
        )
    try:
        server = validate_workload_id(identity)
        peers = [validate_workload_id(client) for client in clients]
    except (ArgumentError, WorkloadIdentityError) as error:
        raise InternalHTTPMTLSConfigError(
            "invalid SPIFFE identity configuration"
        ) from error
    if any(peer.trust_domain != server.trust_domain for peer in peers):
        raise InternalHTTPMTLSConfigError(
            "client identities must use the local trust domain"
        )
    if identity not in clients:
        raise InternalHTTPMTLSConfigError(
            "the local probe identity must be explicitly allowed"
        )
    return InternalHTTPMTLSConfig(socket, identity, frozenset(clients))


def probe(path: str, port: int, environ: Mapping[str, str]) -> bool:
    """Authenticate the backend before sending any HTTP bytes, even on loopback."""
    if path not in PROBE_PATHS or not 1 <= port <= 65535:
        raise InternalHTTPMTLSConfigError("invalid health probe target")
    config = load_internal_http_mtls(environ)
    if config is None:
        connection = http.client.HTTPConnection(PROBE_HOST, port, timeout=1)
        try:
            connection.request("GET", path)
            return connection.getresponse().status == HTTPStatus.OK
        except (OSError, http.client.HTTPException):
            return False
        finally:
            connection.close()
    source = WorkloadContexts.connect(
        config.socket_path, config.server_identity, server=False, timeout=1.0
    )
    try:
        generation = source.current()
        secure_connection = http.client.HTTPSConnection(
            PROBE_HOST, port, timeout=1, context=generation.context
        )
        try:
            secure_connection.connect()
            if secure_connection.sock is None:
                return False
            der = secure_connection.sock.getpeercert(binary_form=True)
            if not der:
                return False
            now = datetime.now(UTC)
            verified_chain = secure_connection.sock.get_verified_chain()
            if not verified_chain or verified_chain[0] != der:
                return False
            chain_deadline(
                [x509.load_der_x509_certificate(item) for item in verified_chain], now
            )
            authorize_verified_leaf(
                x509.load_der_x509_certificate(der),
                frozenset({config.server_identity}),
                now,
            )
            secure_connection.request("GET", path)
            return secure_connection.getresponse().status == HTTPStatus.OK
        except (OSError, ValueError, WorkloadIdentityError, http.client.HTTPException):
            return False
        finally:
            secure_connection.close()
    finally:
        source.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.server.internal_mtls")
    commands = parser.add_subparsers(dest="command", required=True)
    probe_parser = commands.add_parser("probe")
    probe_parser.add_argument("path", choices=PROBE_PATHS)
    probe_parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    try:
        healthy = probe(args.path, args.port, os.environ)
    except (WorkloadIdentityError, X509SourceError, ArgumentError, OSError) as error:
        sys.stderr.write(f"internal health probe unavailable: {type(error).__name__}\n")
        return 2
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
