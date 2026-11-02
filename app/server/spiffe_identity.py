"""SPIFFE identity boundary draft; not an independently deployable listener.

Callers must perform TLS chain verification before authorizing a peer. Only the
worker transport may call this boundary, never an HTTP-header adapter.
"""

from __future__ import annotations

import ssl
import tempfile
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from spiffe import X509Source
from spiffe.spiffe_id.spiffe_id import SpiffeId, SpiffeIdError


class WorkloadIdentityError(RuntimeError):
    """Identity is unavailable or not authorized; never downgrade to plaintext."""


def validate_workload_id(value: str) -> SpiffeId:
    """Reject controls and SDK parse failures as WorkloadIdentityError.

    The pinned SDK raises SpiffeIdError (not ArgumentError) for malformed input;
    converting it here keeps every caller on the fail-closed domain error.
    """
    if any(ord(character) <= 32 or ord(character) == 127 for character in value):
        raise WorkloadIdentityError("workload identity contains whitespace or controls")
    try:
        identity = SpiffeId(value)
    except SpiffeIdError as error:
        raise WorkloadIdentityError(
            "workload identity is not a valid SPIFFE ID"
        ) from error
    if not identity.path:
        raise WorkloadIdentityError("workload identity must have a path")
    return identity


def chain_deadline(certificates: Sequence[x509.Certificate], now: datetime) -> datetime:
    """Bound connection authority by every certificate in its verified path."""
    if not certificates:
        raise WorkloadIdentityError("verified certificate chain is missing")
    if any(
        not cert.not_valid_before_utc <= now < cert.not_valid_after_utc
        for cert in certificates
    ):
        raise WorkloadIdentityError("certificate chain is outside its validity")
    return min(cert.not_valid_after_utc for cert in certificates)


def authorize_verified_leaf(
    leaf: x509.Certificate,
    allowed: frozenset[str],
    now: datetime,
) -> str:
    """Check leaf profile and exact URI after successful TLS chain validation."""
    if not leaf.not_valid_before_utc <= now < leaf.not_valid_after_utc:
        raise WorkloadIdentityError("workload certificate is outside its validity")
    try:
        san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        constraints = leaf.extensions.get_extension_for_class(x509.BasicConstraints)
        usage = leaf.extensions.get_extension_for_class(x509.KeyUsage)
    except x509.ExtensionNotFound as error:
        raise WorkloadIdentityError(
            "workload certificate lacks required extension"
        ) from error
    uris = san.value.get_values_for_type(x509.UniformResourceIdentifier)
    if len(uris) != 1 or uris[0] not in allowed:
        raise WorkloadIdentityError("peer workload identity is not authorized")
    validate_workload_id(uris[0])
    if constraints.value.ca or not usage.value.digital_signature:
        raise WorkloadIdentityError("invalid workload leaf certificate")
    if usage.value.key_cert_sign or usage.value.crl_sign:
        raise WorkloadIdentityError("workload leaf has certificate-signing authority")
    return uris[0]


@dataclass(frozen=True, slots=True)
class TLSGeneration:
    """An immutable identity and trust snapshot, replaced rather than mutated."""

    context: ssl.SSLContext
    fingerprint: bytes
    expires_at: datetime


class WorkloadContexts:
    """Adapt coherent SDK snapshots to fresh stdlib TLS contexts.

    Construct after Gunicorn forks. SDK owns its watch connection and threads;
    close this object on worker shutdown. No SDK objects exist in the master.
    This draft deliberately has no module-global source or application lifespan
    integration. The worker must reject new and existing HTTP dispatch whenever
    current() raises, and must reject older TLS generations after rotation.
    """

    def __init__(
        self, source: X509Source, server_identity: str, *, server: bool = True
    ) -> None:
        self._source = source
        self._server = server
        self._identity = validate_workload_id(server_identity)
        self._allowed_self = frozenset({server_identity})
        self._lock = threading.Lock()
        self._current: TLSGeneration | None = None

    @classmethod
    def connect(
        cls,
        socket_path: str,
        server_identity: str,
        *,
        server: bool = True,
        timeout: float = 5.0,
    ) -> WorkloadContexts:
        # Public verified-chain access was added in Python 3.13; canonical
        # production is 3.14. Never downgrade chain validation on older Python.
        if not callable(getattr(ssl.SSLObject, "get_verified_chain", None)):
            raise WorkloadIdentityError(
                "SPIFFE transport requires public TLS verified-chain access"
            )
        # Validate before opening the Workload API connection.
        validate_workload_id(server_identity)
        source = X509Source(socket_path=socket_path, timeout_in_seconds=timeout)
        return cls(source, server_identity, server=server)

    def current(self) -> TLSGeneration:
        """Fail closed on SDK closure, expiry, invalid material or missing bundle.

        get_x509_context() is the nondeprecated, coherent SDK read: separate
        svid/bundle reads could combine different rotations. No subscriber
        exception is relied on; SDK subscriber exceptions are logged/swallowed.
        """
        with self._lock:
            snapshot = self._source.get_x509_context()
            svid = snapshot.default_svid
            now = datetime.now(UTC)
            authorize_verified_leaf(svid.leaf, self._allowed_self, now)
            bundle = snapshot.x509_bundle_set.get_bundle_for_trust_domain(
                self._identity.trust_domain
            )
            if bundle is None or not bundle.x509_authorities:
                raise WorkloadIdentityError("local workload trust bundle is missing")
            # Conservatively bound own identity by the whole local bundle too:
            # do not guess which valid issuer path a remote client will select.
            expires_at = min(
                chain_deadline(svid.cert_chain, now),
                *(
                    authority.not_valid_after_utc
                    for authority in bundle.x509_authorities
                ),
            )
            if now >= expires_at:
                raise WorkloadIdentityError(
                    "local workload trust authority has expired"
                )
            # Never merge federated authorities into the local-domain verifier.
            chain = b"".join(
                cert.public_bytes(Encoding.PEM) for cert in svid.cert_chain
            )
            authorities = b"".join(
                sorted(
                    cert.public_bytes(Encoding.PEM) for cert in bundle.x509_authorities
                )
            )
            own_public = svid.private_key.public_key().public_bytes(
                Encoding.DER, PublicFormat.SubjectPublicKeyInfo
            )
            leaf_public = svid.leaf.public_key().public_bytes(
                Encoding.DER, PublicFormat.SubjectPublicKeyInfo
            )
            if own_public != leaf_public:
                raise WorkloadIdentityError("workload private key does not match leaf")
            fingerprint = sha256(chain + authorities).digest()
            if self._current is not None and self._current.fingerprint == fingerprint:
                return self._current
            context = ssl.SSLContext(
                ssl.PROTOCOL_TLS_SERVER if self._server else ssl.PROTOCOL_TLS_CLIENT
            )
            if not self._server:
                context.check_hostname = False
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.verify_mode = ssl.CERT_REQUIRED
            context.verify_flags |= ssl.VERIFY_X509_STRICT
            context.options |= ssl.OP_NO_TICKET | ssl.OP_NO_RENEGOTIATION
            if self._server:
                context.num_tickets = 0
            context.set_alpn_protocols(["http/1.1"])
            context.load_verify_locations(cadata=authorities.decode("ascii"))
            # stdlib load_cert_chain requires paths. Private temporary directory
            # and files are removed before publication; production needs tmpfs.
            with tempfile.TemporaryDirectory(prefix="ue-workload-") as directory:
                certfile = Path(directory) / "chain.pem"
                keyfile = Path(directory) / "key.pem"
                with certfile.open("xb") as stream:
                    certfile.chmod(0o600)
                    stream.write(chain)
                with keyfile.open("xb") as stream:
                    keyfile.chmod(0o600)
                    stream.write(
                        svid.private_key.private_bytes(
                            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
                        )
                    )
                context.load_cert_chain(certfile, keyfile)
            generation = TLSGeneration(context, fingerprint, expires_at)
            self._current = generation
            return generation

    def subscribe(self, callback: Callable[[], None]) -> None:
        """Register the event-loop notification callback before initial read."""
        self._source.subscribe_for_updates(callback)

    def unsubscribe(self, callback: Callable[[], None]) -> None:
        """Detach the notification callback before worker shutdown."""
        self._source.unsubscribe_for_updates(callback)

    def close(self) -> None:
        """Stop the SDK stream and invalidate the last generation."""
        with self._lock:
            self._source.close()
            self._current = None
