"""Adversarial stress-test suite for Milestone 3 (SPIFFE/SPIRE & mTLS zero-trust implementation).

Tests:
1. Header spoofing vulnerability in SPIFFEAuthMiddleware (x-spiffe-id header).
2. Dynamic SSLContext cert rotation / staleness in SVIDManager.
3. Untrusted SPIFFE ID rejection.
4. Missing socket behavior on SVIDManager.
"""

from __future__ import annotations

import os
import ssl
from datetime import UTC
from unittest.mock import MagicMock

import pytest
from starlette.responses import PlainTextResponse

from app.core.security.spiffe import (
    SPIFFEAuthMiddleware,
    SVIDManager,
    create_spiffe_client_ssl_context,
    create_spiffe_server_ssl_context,
)


def generate_self_signed_pem() -> tuple[bytes, bytes]:
    """Helper to generate a valid self-signed X.509 certificate and private key PEM pair."""
    from datetime import datetime, timedelta

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "university.ecosystem"),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


@pytest.mark.asyncio
async def test_header_spoofing_vulnerability_in_spiffe_middleware():
    """Vulnerability Test 1: Verify whether SPIFFEAuthMiddleware accepts x-spiffe-id from unauthenticated client headers."""

    async def dummy_app(scope, receive, send):
        response = PlainTextResponse("Secret Internal Data")
        await response(scope, receive, send)

    middleware = SPIFFEAuthMiddleware(
        app=dummy_app,
        allowed_spiffe_ids=["spiffe://university.ecosystem/ns/default/sa/gateway"],
        protected_prefixes=("/api/internal",),
        enabled=True,
    )

    # Scenario A: Request without client TLS cert AND without x-spiffe-id header
    scope_no_cert = {
        "type": "http",
        "method": "GET",
        "path": "/api/internal/secret-data",
        "headers": [],
    }
    sent_messages_a = []

    async def send_a(message):
        sent_messages_a.append(message)

    await middleware(scope_no_cert, None, send_a)
    assert sent_messages_a[0]["status"] == 403

    # Scenario B: SPOOFING ATTACK - Request without client TLS cert BUT with HTTP header x-spiffe-id
    scope_spoofed = {
        "type": "http",
        "method": "GET",
        "path": "/api/internal/secret-data",
        "headers": [
            (b"x-spiffe-id", b"spiffe://university.ecosystem/ns/default/sa/gateway")
        ],
    }
    sent_messages_b = []

    async def send_b(message):
        sent_messages_b.append(message)

    await middleware(scope_spoofed, None, send_b)

    # IF the middleware accepts header spoofing, sent_messages_b will be 200 (dummy_app response)
    # FOR SECURE ZERO TRUST: Header spoofing MUST BE REJECTED (status 403).
    is_vulnerable_to_spoofing = sent_messages_b[0]["status"] == 200
    print(
        f"\n[EMPIRICAL TEST] Header Spoofing Vulnerability Present: {is_vulnerable_to_spoofing}"
    )

    # Assert status is 403 (this will fail if vulnerable, empirically confirming the bug)
    assert sent_messages_b[0]["status"] == 403, (
        "CRITICAL SECURITY BUG: SPIFFEAuthMiddleware accepted untrusted HTTP header x-spiffe-id!"
    )


@pytest.mark.asyncio
async def test_untrusted_spiffe_id_rejection():
    """Verify that SPIFFEAuthMiddleware rejects untrusted SPIFFE IDs from peercert."""

    async def dummy_app(scope, receive, send):
        response = PlainTextResponse("Secret Internal Data")
        await response(scope, receive, send)

    middleware = SPIFFEAuthMiddleware(
        app=dummy_app,
        allowed_spiffe_ids=["spiffe://university.ecosystem/ns/default/sa/gateway"],
        protected_prefixes=("/api/internal",),
        enabled=True,
    )

    # Mock transport with untrusted peer cert
    mock_transport = MagicMock()
    mock_transport.get_extra_info.return_value = {
        "subjectAltName": [
            ("URI", "spiffe://university.ecosystem/ns/default/sa/attacker")
        ]
    }

    scope_untrusted = {
        "type": "http",
        "method": "GET",
        "path": "/api/internal/secret-data",
        "headers": [],
        "transport": mock_transport,
    }
    sent_messages = []

    async def send(message):
        sent_messages.append(message)

    await middleware(scope_untrusted, None, send)
    assert sent_messages[0]["status"] == 403


def test_svid_manager_missing_socket_graceful_degradation():
    """Test SVIDManager behavior when SPIRE agent socket is missing or invalid."""
    manager = SVIDManager(
        socket_path="/nonexistent/path/to/spire-agent.sock",
        spiffe_id="spiffe://university.ecosystem/ns/default/sa/app",
        enabled=True,
    )
    # Startup should log error/warning but not throw unhandled exception
    manager.start()
    assert manager.get_svid_pem_pair() is None
    assert manager.get_trust_bundle_pem() is None
    manager.stop()


def test_ssl_context_staleness_on_svid_rotation():
    """Test whether SSLContext created by create_spiffe_server_ssl_context updates on SVID renewal."""
    manager = SVIDManager(enabled=True)

    # Mock initial SVID
    mock_source = MagicMock()
    mock_svid_1 = MagicMock()
    mock_svid_1.cert_bytes = b"PEM_CERT_1"
    mock_svid_1.private_key_bytes = b"PEM_KEY_1"
    mock_source.get_s_v_i_d.return_value = mock_svid_1
    mock_source.get_bundle_for_trust_domain.return_value = None
    manager._source = mock_source

    # Mock SSLContext.load_cert_chain
    with pytest.MonkeyPatch.context() as mp:
        loaded_certs = []

        def mock_load_cert_chain(self, certfile=None, keyfile=None, password=None):
            cert_val = (
                open(certfile).read()
                if certfile and isinstance(certfile, str) and os.path.exists(certfile)
                else certfile
            )
            key_val = (
                open(keyfile).read()
                if keyfile and isinstance(keyfile, str) and os.path.exists(keyfile)
                else keyfile
            )
            loaded_certs.append((cert_val, key_val))

        mp.setattr(ssl.SSLContext, "load_cert_chain", mock_load_cert_chain)

        _ = create_spiffe_server_ssl_context(manager)
        assert len(loaded_certs) == 1
        assert loaded_certs[0] == ("PEM_CERT_1", "PEM_KEY_1")

        # Now simulate SPIRE agent rotating the SVID certificate (1h TTL renewal)
        mock_svid_2 = MagicMock()
        mock_svid_2.cert_bytes = b"PEM_CERT_2_ROTATED"
        mock_svid_2.private_key_bytes = b"PEM_KEY_2_ROTATED"
        mock_source.get_s_v_i_d.return_value = mock_svid_2

        # Verify that existing `ctx` (SSLContext) still retains initial loaded_certs[0]
        # and create_spiffe_server_ssl_context returns a static SSLContext without SNI/cert reload callbacks.
        print(f"\n[EMPIRICAL TEST] Initial SSLContext loaded cert: {loaded_certs[0]}")
        print(
            f"\n[EMPIRICAL TEST] Active SVID in SVIDManager updated: cert_bytes={manager.get_svid_pem_pair()[0]}"
        )

        # Verify that existing SSLContext `ctx` was NOT automatically updated upon SVID rotation
        assert len(loaded_certs) == 1, (
            "SSLContext does not dynamically track SVID rotation; requires manual SSLContext re-creation on certificate change."
        )


def test_create_spiffe_ssl_context_with_valid_certs_and_trust_bundle():
    """Verify create_spiffe_server_ssl_context and create_spiffe_client_ssl_context with valid PEM certs and cadata."""
    cert_pem, key_pem = generate_self_signed_pem()

    manager = SVIDManager(enabled=True)
    mock_source = MagicMock()
    mock_svid = MagicMock()
    mock_svid.cert_bytes = cert_pem
    mock_svid.private_key_bytes = key_pem
    mock_source.get_s_v_i_d.return_value = mock_svid

    mock_bundle = MagicMock()
    mock_bundle.x509_certs_bytes = cert_pem
    mock_source.get_bundle_for_trust_domain.return_value = mock_bundle
    manager._source = mock_source

    # Test server context construction with real SSLContext
    server_ctx = create_spiffe_server_ssl_context(manager)
    assert isinstance(server_ctx, ssl.SSLContext)
    assert server_ctx.verify_mode == ssl.CERT_REQUIRED

    # Test client context construction with real SSLContext
    client_ctx = create_spiffe_client_ssl_context(manager)
    assert isinstance(client_ctx, ssl.SSLContext)
    assert client_ctx.verify_mode == ssl.CERT_REQUIRED


def test_svid_manager_get_active_svid_and_lock():
    """Verify get_active_svid returns active SVID and manager lock is thread-safe RLock."""
    manager = SVIDManager(enabled=True)
    assert hasattr(manager, "_lock")

    mock_source = MagicMock()
    mock_svid = MagicMock()
    mock_svid.cert_bytes = b"CERT_PEM_BYTES"
    mock_svid.private_key_bytes = b"KEY_PEM_BYTES"
    mock_source.get_s_v_i_d.return_value = mock_svid
    manager._source = mock_source

    pair = manager.get_active_svid()
    assert pair == (b"CERT_PEM_BYTES", b"KEY_PEM_BYTES")


def test_sni_callback_reload_under_lock():
    """Verify SNI callback reloads updated SVID into SSLContext under lock."""
    manager = SVIDManager(enabled=True)
    mock_source = MagicMock()
    mock_svid_1 = MagicMock()
    mock_svid_1.cert_bytes = b"CERT_1"
    mock_svid_1.private_key_bytes = b"KEY_1"
    mock_source.get_s_v_i_d.return_value = mock_svid_1
    manager._source = mock_source

    with pytest.MonkeyPatch.context() as mp:
        loaded_certs = []

        def mock_load_cert_chain(self, certfile=None, keyfile=None, password=None):
            cert_val = (
                open(certfile).read()
                if certfile and isinstance(certfile, str) and os.path.exists(certfile)
                else certfile
            )
            key_val = (
                open(keyfile).read()
                if keyfile and isinstance(keyfile, str) and os.path.exists(keyfile)
                else keyfile
            )
            loaded_certs.append((cert_val, key_val))

        mp.setattr(ssl.SSLContext, "load_cert_chain", mock_load_cert_chain)

        ctx = create_spiffe_server_ssl_context(manager)
        assert len(loaded_certs) == 1
        assert loaded_certs[0] == ("CERT_1", "KEY_1")

        # Simulate rotation
        mock_svid_2 = MagicMock()
        mock_svid_2.cert_bytes = b"CERT_2_ROTATED"
        mock_svid_2.private_key_bytes = b"KEY_2_ROTATED"
        mock_source.get_s_v_i_d.return_value = mock_svid_2

        # Trigger SNI callback
        if hasattr(ctx, "sni_callback") and ctx.sni_callback:
            ctx.sni_callback(MagicMock(), "example.com", ctx)

        assert len(loaded_certs) == 2
        assert loaded_certs[1] == ("CERT_2_ROTATED", "KEY_2_ROTATED")


def test_get_server_and_client_ssl_context_dynamic_reload():
    """Verify get_server_ssl_context and get_client_ssl_context fetch current active SVID."""
    manager = SVIDManager(enabled=True)
    mock_source = MagicMock()
    mock_svid_1 = MagicMock()
    mock_svid_1.cert_bytes = b"CERT_1"
    mock_svid_1.private_key_bytes = b"KEY_1"
    mock_source.get_s_v_i_d.return_value = mock_svid_1
    manager._source = mock_source

    with pytest.MonkeyPatch.context() as mp:
        loaded_certs = []

        def mock_load_cert_chain(self, certfile=None, keyfile=None, password=None):
            cert_val = (
                open(certfile).read()
                if certfile and isinstance(certfile, str) and os.path.exists(certfile)
                else certfile
            )
            key_val = (
                open(keyfile).read()
                if keyfile and isinstance(keyfile, str) and os.path.exists(keyfile)
                else keyfile
            )
            loaded_certs.append((cert_val, key_val))

        mp.setattr(ssl.SSLContext, "load_cert_chain", mock_load_cert_chain)

        _ = manager.get_client_ssl_context()
        assert len(loaded_certs) == 1
        assert loaded_certs[0] == ("CERT_1", "KEY_1")

        # Rotate SVID
        mock_svid_2 = MagicMock()
        mock_svid_2.cert_bytes = b"CERT_2_ROTATED"
        mock_svid_2.private_key_bytes = b"KEY_2_ROTATED"
        mock_source.get_s_v_i_d.return_value = mock_svid_2

        _ = manager.get_server_ssl_context()
        assert len(loaded_certs) == 2
        assert loaded_certs[1] == ("CERT_2_ROTATED", "KEY_2_ROTATED")
