"""SDK snapshot/context adaptation, separate from required live SPIRE proof."""

from __future__ import annotations

import ssl
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from spiffe import X509Source
from spiffe.bundle.x509_bundle.x509_bundle import X509Bundle
from spiffe.bundle.x509_bundle.x509_bundle_set import X509BundleSet
from spiffe.spiffe_id.spiffe_id import SpiffeId, TrustDomain
from spiffe.svid.x509_svid import X509Svid
from spiffe.workloadapi.errors import X509SourceError
from spiffe.workloadapi.x509_context import X509Context

from app.server import spiffe_identity
from app.server.spiffe_identity import WorkloadContexts, WorkloadIdentityError
from tests.test_spiffe_identity import IDENTITY, NOW, leaf


def snapshot(identity: str = IDENTITY) -> X509Context:
    key = ec.generate_private_key(ec.SECP256R1())
    certificate = leaf((identity,), private_key=key)
    svid = X509Svid(SpiffeId(identity), [certificate], key)
    authority = leaf(
        ("spiffe://university.ecosystem/test-root",), ca=True, key_cert_sign=True
    )
    bundle = X509Bundle(TrustDomain("university.ecosystem"), {authority})
    return X509Context([svid], X509BundleSet.of([bundle]))


@pytest.fixture
def sdk(monkeypatch: pytest.MonkeyPatch) -> Mock:
    source = Mock(spec=X509Source)
    source.get_x509_context.return_value = snapshot()
    clock = Mock()
    clock.now.return_value = NOW
    monkeypatch.setattr(spiffe_identity, "datetime", clock)
    return source


def test_snapshot_rotation_replaces_context_not_mutates(sdk: Mock) -> None:
    provider = WorkloadContexts(sdk, IDENTITY)
    first = provider.current()
    assert first.context.verify_mode == ssl.CERT_REQUIRED
    assert provider.current() is first
    sdk.get_x509_context.return_value = snapshot()
    second = provider.current()
    assert second.context is not first.context
    assert second.fingerprint != first.fingerprint
    assert first.context.verify_mode == ssl.CERT_REQUIRED


def test_bundle_removal_cannot_reuse_cached_context(sdk: Mock) -> None:
    provider = WorkloadContexts(sdk, IDENTITY)
    first = provider.current()
    old = sdk.get_x509_context.return_value
    sdk.get_x509_context.return_value = X509Context(
        old.x509_svids, X509BundleSet.of([])
    )
    with pytest.raises(WorkloadIdentityError, match="trust bundle"):
        provider.current()
    assert first.context.verify_mode == ssl.CERT_REQUIRED


def test_federated_authority_cannot_replace_local_bundle(sdk: Mock) -> None:
    old = sdk.get_x509_context.return_value
    authority = leaf(("spiffe://elsewhere.test/root",), ca=True, key_cert_sign=True)
    sdk.get_x509_context.return_value = X509Context(
        old.x509_svids,
        X509BundleSet.of([X509Bundle(TrustDomain("elsewhere.test"), {authority})]),
    )
    with pytest.raises(WorkloadIdentityError, match="trust bundle"):
        WorkloadContexts(sdk, IDENTITY).current()


def test_wrong_server_identity_is_rejected(sdk: Mock) -> None:
    sdk.get_x509_context.return_value = snapshot(IDENTITY + "/impostor")
    with pytest.raises(WorkloadIdentityError):
        WorkloadContexts(sdk, IDENTITY).current()


def test_private_key_mismatch_is_rejected(sdk: Mock) -> None:
    old = sdk.get_x509_context.return_value
    bad_svid = X509Svid(
        SpiffeId(IDENTITY),
        old.default_svid.cert_chain,
        ec.generate_private_key(ec.SECP256R1()),
    )
    sdk.get_x509_context.return_value = X509Context([bad_svid], old.x509_bundle_set)
    with pytest.raises(WorkloadIdentityError, match="private key"):
        WorkloadContexts(sdk, IDENTITY).current()


def test_source_error_does_not_return_cached_material(sdk: Mock) -> None:
    provider = WorkloadContexts(sdk, IDENTITY)
    provider.current()
    sdk.get_x509_context.side_effect = X509SourceError("closed")
    with pytest.raises(X509SourceError):
        provider.current()


def test_expiry_cannot_reuse_cached_generation(sdk: Mock) -> None:
    provider = WorkloadContexts(sdk, IDENTITY)
    provider.current()
    spiffe_identity.datetime.now.return_value = NOW + timedelta(minutes=1)
    with pytest.raises(WorkloadIdentityError):
        provider.current()


def test_client_context_uses_uri_not_dns_validation(sdk: Mock) -> None:
    context = WorkloadContexts(sdk, IDENTITY, server=False).current().context
    assert context.protocol == ssl.PROTOCOL_TLS_CLIENT
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert not context.check_hostname


def test_temporary_key_material_removed_before_publication(
    sdk: Mock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    factory = tempfile.TemporaryDirectory
    monkeypatch.setattr(
        spiffe_identity.tempfile,
        "TemporaryDirectory",
        lambda **kwargs: factory(dir=tmp_path, **kwargs),
    )
    WorkloadContexts(sdk, IDENTITY).current()
    assert list(tmp_path.iterdir()) == []


def test_connection_is_bounded_and_close_owns_sdk(
    monkeypatch: pytest.MonkeyPatch, sdk: Mock
) -> None:
    factory = Mock(return_value=sdk)
    monkeypatch.setattr(spiffe_identity, "X509Source", factory)
    provider = WorkloadContexts.connect("unix:///spire/agent.sock", IDENTITY)
    factory.assert_called_once_with(
        socket_path="unix:///spire/agent.sock", timeout_in_seconds=5.0
    )
    callback = Mock()
    provider.subscribe(callback)
    provider.unsubscribe(callback)
    provider.close()
    sdk.subscribe_for_updates.assert_called_once_with(callback)
    sdk.unsubscribe_for_updates.assert_called_once_with(callback)
    sdk.close.assert_called_once()


def test_local_bundle_expiry_limits_server_generation(sdk: Mock) -> None:
    old = sdk.get_x509_context.return_value
    authority = leaf(
        ("spiffe://university.ecosystem/test-ca",),
        ca=True,
        key_cert_sign=True,
        valid_until=NOW + timedelta(seconds=30),
    )
    sdk.get_x509_context.return_value = X509Context(
        old.x509_svids,
        X509BundleSet.of(
            [X509Bundle(TrustDomain("university.ecosystem"), {authority})]
        ),
    )
    assert WorkloadContexts(sdk, IDENTITY).current().expires_at == NOW + timedelta(
        seconds=30
    )


def test_expired_local_authority_rejects_still_valid_svid(sdk: Mock) -> None:
    old = sdk.get_x509_context.return_value
    authority = leaf(
        ("spiffe://university.ecosystem/test-ca",),
        ca=True,
        key_cert_sign=True,
        valid_until=NOW + timedelta(seconds=30),
    )
    sdk.get_x509_context.return_value = X509Context(
        old.x509_svids,
        X509BundleSet.of(
            [X509Bundle(TrustDomain("university.ecosystem"), {authority})]
        ),
    )
    provider = WorkloadContexts(sdk, IDENTITY)
    first = provider.current()
    spiffe_identity.datetime.now.return_value = NOW + timedelta(seconds=30)
    with pytest.raises(WorkloadIdentityError, match="trust authority has expired"):
        provider.current()
    assert first.context.verify_mode == ssl.CERT_REQUIRED


def test_missing_public_chain_api_fails_before_opening_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(
        spiffe_identity.ssl.SSLObject, "get_verified_chain", raising=False
    )
    factory = Mock()
    monkeypatch.setattr(spiffe_identity, "X509Source", factory)
    with pytest.raises(WorkloadIdentityError, match="verified-chain access"):
        WorkloadContexts.connect("unix:///spire/agent.sock", IDENTITY)
    factory.assert_not_called()
