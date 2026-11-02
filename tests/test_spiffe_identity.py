"""Draft leaf-authorization tests; these do NOT prove SPIRE issuance/rotation."""

from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.server.spiffe_identity import WorkloadIdentityError, authorize_verified_leaf

IDENTITY = "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway"
NOW = datetime(2026, 11, 2, tzinfo=UTC)


def leaf(
    uris: tuple[str, ...],
    *,
    ca: bool = False,
    digital_signature: bool = True,
    key_cert_sign: bool = False,
    crl_sign: bool = False,
    include_san: bool = True,
    include_usage: bool = True,
    include_constraints: bool = True,
    private_key: ec.EllipticCurvePrivateKey | None = None,
    valid_until: datetime | None = None,
) -> x509.Certificate:
    key = private_key or ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "unit-test-only")])
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW)
        .not_valid_after(valid_until or NOW + timedelta(minutes=1))
    )
    if include_san:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(
                [x509.UniformResourceIdentifier(uri) for uri in uris]
            ),
            critical=False,
        )
    if include_constraints:
        builder = builder.add_extension(
            x509.BasicConstraints(ca=ca, path_length=None), critical=True
        )
    if include_usage:
        builder = builder.add_extension(
            x509.KeyUsage(
                digital_signature=digital_signature,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=key_cert_sign,
                crl_sign=crl_sign,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
    return builder.sign(key, hashes.SHA256())


def test_exact_identity_at_not_before_is_authorized() -> None:
    assert (
        authorize_verified_leaf(leaf((IDENTITY,)), frozenset({IDENTITY}), NOW)
        == IDENTITY
    )


@pytest.mark.parametrize(
    "uris", [(), (IDENTITY, IDENTITY), (IDENTITY, "urn:other"), (IDENTITY + "/child",)]
)
def test_missing_multiple_or_prefix_identity_is_rejected(uris: tuple[str, ...]) -> None:
    with pytest.raises(WorkloadIdentityError):
        authorize_verified_leaf(leaf(uris), frozenset({IDENTITY}), NOW)


@pytest.mark.parametrize("offset", [-1, 60, 61])
def test_validity_is_closed_at_expiry(offset: int) -> None:
    with pytest.raises(WorkloadIdentityError):
        authorize_verified_leaf(
            leaf((IDENTITY,)), frozenset({IDENTITY}), NOW + timedelta(seconds=offset)
        )


@pytest.mark.parametrize(
    "options",
    [
        {"ca": True},
        {"digital_signature": False},
        {"key_cert_sign": True},
        {"crl_sign": True},
        {"include_san": False},
        {"include_usage": False},
        {"include_constraints": False},
    ],
)
def test_invalid_leaf_profile_is_rejected(options: dict[str, bool]) -> None:
    with pytest.raises(WorkloadIdentityError):
        authorize_verified_leaf(
            leaf((IDENTITY,), **options), frozenset({IDENTITY}), NOW
        )


def test_trust_domain_root_cannot_be_a_workload() -> None:
    identity = "spiffe://university.ecosystem"
    with pytest.raises(WorkloadIdentityError):
        authorize_verified_leaf(leaf((identity,)), frozenset({identity}), NOW)


def test_empty_allowlist_rejects_valid_leaf() -> None:
    with pytest.raises(WorkloadIdentityError):
        authorize_verified_leaf(leaf((IDENTITY,)), frozenset(), NOW)


@pytest.mark.parametrize("suffix", ["\n", "\r", "\t", "\x00", "\x7f", " "])
def test_control_suffix_is_rejected_even_if_allowlist_contains_it(suffix: str) -> None:
    from app.server.spiffe_identity import validate_workload_id

    with pytest.raises(WorkloadIdentityError):
        validate_workload_id(IDENTITY + suffix)
