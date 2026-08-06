"""Empirical stress test suite for SPIFFE SVIDManager, SSLContext builders, and _reload_on_sni.

Stress tests concurrent TLS handshakes against Python `SVIDManager` and `_reload_on_sni` under parallel thread execution.
Verifies zero `KEY_VALUES_MISMATCH` or `NO_PRIVATE_KEY_ASSIGNED` errors under high-concurrency certificate rotations.
"""

from __future__ import annotations

import socket
import ssl
import sys
import threading
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

sys.path.insert(0, ".")

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.core.security.spiffe import (
    SVIDManager,
    create_spiffe_client_ssl_context,
    create_spiffe_server_ssl_context,
)


def generate_ca_and_cert_key_pairs(
    num_pairs: int = 5,
) -> tuple[bytes, list[tuple[bytes, bytes]]]:
    """Generate a shared self-signed CA certificate and N child cert/key pairs signed by that CA."""
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "university.ecosystem CA")]
    )
    ski = x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key())
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(ski, critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM)

    pairs = []
    for _ in range(num_pairs):
        leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        leaf_name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "university.ecosystem")]
        )
        san = x509.SubjectAlternativeName(
            [
                x509.UniformResourceIdentifier(
                    "spiffe://university.ecosystem/ns/default/sa/app"
                )
            ]
        )
        aki = x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key())
        leaf_cert = (
            x509.CertificateBuilder()
            .subject_name(leaf_name)
            .issuer_name(ca_name)
            .public_key(leaf_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC) - timedelta(days=1))
            .not_valid_after(datetime.now(UTC) + timedelta(days=1))
            .add_extension(san, critical=False)
            .add_extension(aki, critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        cert_pem = leaf_cert.public_bytes(serialization.Encoding.PEM) + ca_pem
        key_pem = leaf_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pairs.append((cert_pem, key_pem))

    return ca_pem, pairs


class MockX509Source:
    """Mock X509Source supporting dynamic SVID rotation."""

    def __init__(self, ca_pem: bytes, pairs: list[tuple[bytes, bytes]]):
        self.ca_pem = ca_pem
        self.pairs = pairs
        self.index = 0
        self.lock = threading.Lock()

    def rotate(self):
        with self.lock:
            self.index = (self.index + 1) % len(self.pairs)

    def get_s_v_i_d(self):
        with self.lock:
            cert_pem, key_pem = self.pairs[self.index]
        mock_svid = MagicMock()
        mock_svid.cert_bytes = cert_pem
        mock_svid.private_key_bytes = key_pem
        return mock_svid

    def get_bundle_for_trust_domain(self, trust_domain):
        mock_bundle = MagicMock()
        mock_bundle.x509_certs_bytes = self.ca_pem
        return mock_bundle


def run_mtls_concurrency_stress_test(
    num_threads: int = 20,
    handshakes_per_thread: int = 40,
    rotation_interval_sec: float = 0.005,
) -> dict:
    """Execute high-concurrency mTLS handshakes during continuous SVID cert rotation."""
    total_attempted = num_threads * handshakes_per_thread
    print("\n=======================================================")
    print("STARTING SPIFFE mTLS CONCURRENCY STRESS TEST")
    print(
        f"Threads: {num_threads}, Handshakes/thread: {handshakes_per_thread}, Total: {total_attempted}"
    )
    print(f"SVID rotation interval: {rotation_interval_sec * 1000:.1f}ms")
    print("=======================================================")

    ca_pem, pairs = generate_ca_and_cert_key_pairs(num_pairs=5)
    source = MockX509Source(ca_pem, pairs)

    manager = SVIDManager(enabled=True)
    manager._source = source
    manager.spiffe_id_str = "spiffe://university.ecosystem/ns/default/sa/app"

    server_ctx = create_spiffe_server_ssl_context(manager)
    server_ctx.verify_mode = ssl.CERT_NONE

    client_ctx = create_spiffe_client_ssl_context(manager)
    client_ctx.check_hostname = False
    client_ctx.verify_mode = ssl.CERT_NONE

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(256)
    server_port = server_sock.getsockname()[1]

    stop_event = threading.Event()
    error_counter = Counter()
    success_count = 0
    lock = threading.Lock()

    def rotator_thread():
        """Continuously rotate active SVID in background."""
        while not stop_event.is_set():
            source.rotate()
            time.sleep(rotation_interval_sec)

    def server_worker(client_conn):
        nonlocal success_count
        try:
            ssl_conn = server_ctx.wrap_socket(
                client_conn,
                server_side=True,
                do_handshake_on_connect=False,
            )
            ssl_conn.do_handshake()
            ssl_conn.close()
            with lock:
                success_count += 1
        except Exception as exc:
            err_msg = str(exc)
            err_type = type(exc).__name__
            with lock:
                error_counter[f"Server {err_type}: {err_msg}"] += 1
        finally:
            try:
                client_conn.close()
            except OSError:
                pass

    def listener_thread():
        while not stop_event.is_set():
            try:
                server_sock.settimeout(0.1)
                client_conn, _ = server_sock.accept()
                t = threading.Thread(
                    target=server_worker, args=(client_conn,), daemon=True
                )
                t.start()
            except TimeoutError:
                continue
            except OSError:
                break

    rot_t = threading.Thread(target=rotator_thread, daemon=True)
    list_t = threading.Thread(target=listener_thread, daemon=True)
    rot_t.start()
    list_t.start()

    def client_worker():
        for _ in range(handshakes_per_thread):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                c_ctx = manager.get_client_ssl_context()
                c_ctx.check_hostname = False
                c_ctx.verify_mode = ssl.CERT_NONE
                ssl_s = c_ctx.wrap_socket(
                    s,
                    server_hostname="university.ecosystem",
                    do_handshake_on_connect=False,
                )
                ssl_s.connect(("127.0.0.1", server_port))
                ssl_s.do_handshake()
                ssl_s.close()
            except Exception as exc:
                err_msg = str(exc)
                err_type = type(exc).__name__
                with lock:
                    error_counter[f"Client {err_type}: {err_msg}"] += 1

    threads = []
    start_time = time.time()
    for _ in range(num_threads):
        t = threading.Thread(target=client_worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    duration = time.time() - start_time
    stop_event.set()
    server_sock.close()
    rot_t.join(timeout=1.0)
    list_t.join(timeout=1.0)

    print("\n--- STRESS TEST SUMMARY ---")
    print(f"Duration: {duration:.2f}s")
    print(f"Handshakes attempted: {total_attempted}")
    print(
        f"Handshakes succeeded: {success_count} ({success_count / total_attempted * 100:.1f}%)"
    )
    print(f"Error count total: {sum(error_counter.values())}")
    for err, count in error_counter.items():
        print(f"  [{count}x] {err}")

    # Explicitly check for target errors: KEY_VALUES_MISMATCH or NO_PRIVATE_KEY_ASSIGNED
    target_errors = []
    for err in error_counter:
        err_upper = err.upper()
        if (
            "KEY_VALUES_MISMATCH" in err_upper
            or "NO_PRIVATE_KEY_ASSIGNED" in err_upper
            or "KEY VALUES MISMATCH" in err_upper
            or "NO PRIVATE KEY ASSIGNED" in err_upper
        ):
            target_errors.append(err)

    print(f"\nTarget fatal key mismatch errors: {target_errors}")

    return {
        "attempted": total_attempted,
        "succeeded": success_count,
        "duration": duration,
        "errors": dict(error_counter),
        "target_errors": target_errors,
    }


def run_parallel_ssl_context_factory_stress(
    num_threads: int = 20, iterations_per_thread: int = 50
) -> dict:
    """Stress test parallel calls to manager.get_server_ssl_context() and manager.get_client_ssl_context()."""
    print("\n=======================================================")
    print("STARTING PARALLEL SSL CONTEXT FACTORY STRESS TEST")
    print(f"Threads: {num_threads}, Iterations/thread: {iterations_per_thread}")
    print("=======================================================")

    ca_pem, pairs = generate_ca_and_cert_key_pairs(num_pairs=5)
    source = MockX509Source(ca_pem, pairs)
    manager = SVIDManager(enabled=True)
    manager._source = source
    manager.spiffe_id_str = "spiffe://university.ecosystem/ns/default/sa/app"

    stop_event = threading.Event()
    error_counter = Counter()

    def rotator():
        while not stop_event.is_set():
            source.rotate()
            time.sleep(0.002)

    rot_t = threading.Thread(target=rotator, daemon=True)
    rot_t.start()

    def worker():
        for _ in range(iterations_per_thread):
            try:
                srv_ctx = manager.get_server_ssl_context()
                cli_ctx = manager.get_client_ssl_context()
                assert isinstance(srv_ctx, ssl.SSLContext)
                assert isinstance(cli_ctx, ssl.SSLContext)
            except Exception as exc:
                err_msg = str(exc)
                err_type = type(exc).__name__
                error_counter[f"{err_type}: {err_msg}"] += 1

    threads = []
    start_t = time.time()
    for _ in range(num_threads):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    stop_event.set()
    rot_t.join(timeout=1.0)
    dur = time.time() - start_t

    total_ops = num_threads * iterations_per_thread * 2
    print(f"Factory stress completed in {dur:.2f}s ({total_ops} context creations)")
    print(f"Errors: {dict(error_counter)}")

    target_errors = [
        err
        for err in error_counter
        if any(
            k in err.upper() for k in ["KEY_VALUES_MISMATCH", "NO_PRIVATE_KEY_ASSIGNED"]
        )
    ]
    return {
        "total_ops": total_ops,
        "errors": dict(error_counter),
        "target_errors": target_errors,
    }


def test_mtls_concurrency_stress():
    """Pytest test case for mTLS concurrency stress."""
    res = run_mtls_concurrency_stress_test(num_threads=20, handshakes_per_thread=40)
    ssl_handshake_errors = [
        err
        for err in res["errors"]
        if "SSLV3_ALERT_HANDSHAKE_FAILURE" in err.upper()
        or "NO_SUITABLE_SIGNATURE_ALGORITHM" in err.upper()
        or "KEY_VALUES_MISMATCH" in err.upper()
        or "NO_PRIVATE_KEY_ASSIGNED" in err.upper()
    ]
    assert not ssl_handshake_errors, (
        f"SSL handshake failures detected: {ssl_handshake_errors}"
    )
    assert res["target_errors"] == []


def test_parallel_ssl_context_factory_stress():
    """Pytest test case for parallel SSLContext factory stress."""
    res = run_parallel_ssl_context_factory_stress(
        num_threads=20, iterations_per_thread=50
    )
    assert res["target_errors"] == []
    assert not res["errors"], (
        f"Unexpected errors during factory stress: {res['errors']}"
    )


if __name__ == "__main__":
    res_mtls = run_mtls_concurrency_stress_test(
        num_threads=20, handshakes_per_thread=40
    )
    res_factory = run_parallel_ssl_context_factory_stress(
        num_threads=20, iterations_per_thread=50
    )
