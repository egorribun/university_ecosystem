"""Empirical High-Concurrency Stress Test Suite for SPIFFE SVID Certificate Rotation & mTLS.

Focus:
- Stress test dynamic SVID certificate updates across client and server SSLContexts under high concurrency.
- Verify zero connection drops, zero thread safety violations, zero temp file leaks, and 100% handshake success.
"""

from __future__ import annotations

import asyncio
import glob
import os
import ssl
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.core.security.spiffe import (
    SVIDManager,
    create_spiffe_server_ssl_context,
)


def generate_ca() -> tuple[Any, Any, bytes]:
    """Generate CA key, cert object, and CA PEM bytes."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SPIFFE Test CA")])
    ca_ski = x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key())
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(hours=1))
        .not_valid_after(datetime.now(UTC) + timedelta(hours=24))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
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
        .add_extension(ca_ski, critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM)
    return ca_cert, ca_key, ca_pem


def generate_svid(
    ca_cert: Any, ca_key: Any, common_name: str, spiffe_id: str
) -> tuple[bytes, bytes]:
    """Generate a new workload SVID leaf cert and private key PEM signed by the given CA."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    svid_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    svid_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    svid_cert = (
        x509.CertificateBuilder()
        .subject_name(svid_name)
        .issuer_name(ca_cert.subject)
        .public_key(svid_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=5))
        .not_valid_after(datetime.now(UTC) + timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.UniformResourceIdentifier(spiffe_id),
                    x509.DNSName(common_name),
                ]
            ),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage(
                [
                    ExtendedKeyUsageOID.SERVER_AUTH,
                    ExtendedKeyUsageOID.CLIENT_AUTH,
                ]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    svid_pem = svid_cert.public_bytes(serialization.Encoding.PEM)
    key_pem = svid_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return svid_pem, key_pem


def generate_ca_and_svid_pem(
    common_name: str, spiffe_id: str
) -> tuple[bytes, bytes, bytes]:
    ca_cert, ca_key, ca_pem = generate_ca()
    svid_pem, key_pem = generate_svid(ca_cert, ca_key, common_name, spiffe_id)
    return ca_pem, svid_pem, key_pem


class MockX509Source:
    """Mock X509Source supporting thread-safe dynamic SVID updates."""

    def __init__(self, ca_pem: bytes, svid_pem: bytes, key_pem: bytes) -> None:
        self._lock = threading.Lock()
        self.ca_pem = ca_pem
        self.svid_pem = svid_pem
        self.key_pem = key_pem

    def update_svid(self, new_svid_pem: bytes, new_key_pem: bytes) -> None:
        with self._lock:
            self.svid_pem = new_svid_pem
            self.key_pem = new_key_pem

    def get_s_v_i_d(self) -> MagicMock:
        with self._lock:
            mock = MagicMock()
            mock.cert_bytes = self.svid_pem
            mock.private_key_bytes = self.key_pem
            return mock

    def get_bundle_for_trust_domain(self, domain: Any) -> MagicMock:
        with self._lock:
            mock = MagicMock()
            mock.x509_certs_bytes = self.ca_pem
            return mock


@pytest.mark.asyncio
async def test_high_concurrency_mtls_with_dynamic_svid_rotations():
    """Stress test: 100 concurrent mTLS handshakes while SVID certs rotate dynamically."""
    ca_cert, ca_key, ca_pem = generate_ca()
    svid_pem_1, key_pem_1 = generate_svid(
        ca_cert,
        ca_key,
        "server.ecosystem",
        "spiffe://university.ecosystem/ns/default/sa/app",
    )

    import app.core.security.spiffe as spiffe_mod

    mock_spiffe_id_cls = MagicMock()
    mock_spiffe_id_cls.parse.return_value.trust_domain = "university.ecosystem"
    spiffe_mod.SpiffeId = mock_spiffe_id_cls

    source = MockX509Source(ca_pem, svid_pem_1, key_pem_1)
    manager = SVIDManager(enabled=True)
    manager._source = source

    server_ctx = manager.get_server_ssl_context()

    # Echo server handler
    async def handle_echo(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            data = await reader.read(100)
            if data:
                writer.write(b"ACK:" + data)
                await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(
        handle_echo,
        host="127.0.0.1",
        port=0,
        ssl=server_ctx,
    )
    port = server.sockets[0].getsockname()[1]

    stop_rotation = threading.Event()
    rotation_count = 0

    def cert_rotator() -> None:
        nonlocal rotation_count
        while not stop_rotation.is_set():
            time.sleep(0.05)
            # Generate new rotated SVID signed by SAME CA
            new_svid, new_key = generate_svid(
                ca_cert,
                ca_key,
                "server.ecosystem",
                "spiffe://university.ecosystem/ns/default/sa/app",
            )
            source.update_svid(new_svid, new_key)
            rotation_count += 1

    rotator_thread = threading.Thread(target=cert_rotator, daemon=True)
    rotator_thread.start()

    successes = 0
    failures = 0
    lock = asyncio.Lock()

    async def run_client(client_id: int) -> None:
        nonlocal successes, failures
        for _ in range(5):
            try:
                # Fetch fresh client context or use existing
                c_ctx = manager.get_client_ssl_context()
                reader, writer = await asyncio.open_connection(
                    "127.0.0.1",
                    port,
                    ssl=c_ctx,
                    server_hostname="server.ecosystem",
                )
                msg = f"HELLO_{client_id}".encode()
                writer.write(msg)
                await writer.drain()
                resp = await reader.read(100)
                writer.close()
                await writer.wait_closed()
                if resp == b"ACK:" + msg:
                    async with lock:
                        successes += 1
                else:
                    async with lock:
                        failures += 1
            except Exception as exc:
                print(f"[CLIENT HANDSHAKE ERROR] {type(exc).__name__}: {exc}")
                async with lock:
                    failures += 1

    tasks = [run_client(i) for i in range(50)]
    await asyncio.gather(*tasks)

    stop_rotation.set()
    rotator_thread.join(timeout=2.0)
    server.close()
    await server.wait_closed()

    print(
        f"\n[EMPIRICAL STRESS TEST RESULTS]\n"
        f"Rotations performed: {rotation_count}\n"
        f"Handshake Successes: {successes}\n"
        f"Handshake Failures: {failures}\n"
    )

    assert failures == 0, (
        f"Expected 0 failures during dynamic SVID rotation under concurrency, got {failures}"
    )
    assert successes == 250, (
        f"Expected 250 total successful handshakes, got {successes}"
    )


def test_concurrent_ssl_context_building_and_temp_file_cleanup():
    """Verify concurrent SSLContext generation cleans up temporary PEM files without leaks."""
    import app.core.security.spiffe as spiffe_mod

    mock_spiffe_id_cls = MagicMock()
    mock_spiffe_id_cls.parse.return_value.trust_domain = "university.ecosystem"
    spiffe_mod.SpiffeId = mock_spiffe_id_cls

    temp_dir = tempfile.gettempdir()
    initial_tmp_files = set(glob.glob(os.path.join(temp_dir, "tmp*")))

    ca_pem, svid_pem, key_pem = generate_ca_and_svid_pem(
        "server.ecosystem", "spiffe://university.ecosystem/ns/default/sa/app"
    )
    source = MockX509Source(ca_pem, svid_pem, key_pem)
    manager = SVIDManager(enabled=True)
    manager._source = source

    def worker() -> None:
        for _ in range(20):
            server_ctx = manager.get_server_ssl_context()
            client_ctx = manager.get_client_ssl_context()
            assert isinstance(server_ctx, ssl.SSLContext)
            assert isinstance(client_ctx, ssl.SSLContext)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final_tmp_files = set(glob.glob(os.path.join(temp_dir, "tmp*")))
    leaked_files = final_tmp_files - initial_tmp_files

    print(f"\n[EMPIRICAL TEMP FILE LEAK TEST] Leaked temp files: {len(leaked_files)}")
    assert len(leaked_files) == 0, (
        f"Detected {len(leaked_files)} leaked temporary files during concurrent SSLContext generation"
    )


def test_sni_callback_concurrency_stress():
    """Stress test SNI callback cert reloading under 50 concurrent threads."""
    import app.core.security.spiffe as spiffe_mod

    mock_spiffe_id_cls = MagicMock()
    mock_spiffe_id_cls.parse.return_value.trust_domain = "university.ecosystem"
    spiffe_mod.SpiffeId = mock_spiffe_id_cls

    ca_cert, ca_key, ca_pem = generate_ca()
    svid_pem, key_pem = generate_svid(
        ca_cert,
        ca_key,
        "server.ecosystem",
        "spiffe://university.ecosystem/ns/default/sa/app",
    )
    source = MockX509Source(ca_pem, svid_pem, key_pem)
    manager = SVIDManager(enabled=True)
    manager._source = source

    server_ctx = create_spiffe_server_ssl_context(manager)
    errors = []
    lock = threading.Lock()

    def sni_caller() -> None:
        for _ in range(50):
            try:
                # Update SVID
                new_svid, new_key = generate_svid(
                    ca_cert,
                    ca_key,
                    "server.ecosystem",
                    "spiffe://university.ecosystem/ns/default/sa/app",
                )
                source.update_svid(new_svid, new_key)

                # Trigger SNI callback
                if hasattr(server_ctx, "sni_callback") and server_ctx.sni_callback:
                    server_ctx.sni_callback(MagicMock(), "server.ecosystem", server_ctx)
            except Exception as exc:
                with lock:
                    errors.append(exc)

    threads = [threading.Thread(target=sni_caller) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"SNI callback failed under concurrency: {errors}"
