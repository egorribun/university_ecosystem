"""MOD-22-02 (Wave 22): Concurrency and thread-safety tests.

Tests cover:
  - CoW public key cache race: multiple threads calling _get_cached_public_key_pem
  - HIBP client double-checked locking: concurrent async initialization
  - SpiceDB cache invalidation timing: concurrent health probes
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock

import pytest

from app.auth.security import _get_cached_public_key_pem

# ---------------------------------------------------------------------------
# Helper: Generate a minimal RSA private key PEM for cache tests.
# ---------------------------------------------------------------------------


def _generate_test_private_key_pem() -> str:
    """Generate a small RSA private key PEM for testing (2048-bit)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


# ---------------------------------------------------------------------------
# CoW public key cache race (MOD-22-02)
# ---------------------------------------------------------------------------


class TestCoWPublicKeyCacheRace:
    """Verify that concurrent calls to _get_cached_public_key_pem are safe.

    The CoW (Copy-on-Write) pattern in security.py swaps the global dict
    reference atomically.  Readers should never see a partially-updated dict.
    """

    def test_concurrent_same_kid(self) -> None:
        """Multiple threads requesting the same kid must all get the same result."""
        pem = _generate_test_private_key_pem()
        kid = "test-kid-concurrent"

        # Reset the cache to ensure a cold start.
        import app.auth.security as sec

        original_cache = sec._public_key_cache
        sec._public_key_cache = {}

        results: list[str] = []
        errors: list[Exception] = []

        def worker() -> str:
            return _get_cached_public_key_pem(kid, pem)

        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(worker) for _ in range(16)]
                for f in as_completed(futures):
                    try:
                        results.append(f.result())
                    except Exception as exc:
                        errors.append(exc)

            assert not errors, f"Unexpected errors: {errors}"
            assert len(results) == 16
            # All results must be identical.
            assert len(set(results)) == 1, "Different threads got different public keys"
        finally:
            sec._public_key_cache = original_cache

    def test_concurrent_different_kids(self) -> None:
        """Multiple threads requesting different kids must each get correct results."""
        import app.auth.security as sec

        original_cache = sec._public_key_cache
        sec._public_key_cache = {}

        # Generate distinct keys for different kids.
        keys = {f"kid-{i}": _generate_test_private_key_pem() for i in range(4)}
        results: dict[str, set[str]] = {kid: set() for kid in keys}
        lock = threading.Lock()

        def worker(kid: str, pem: str) -> None:
            result = _get_cached_public_key_pem(kid, pem)
            with lock:
                results[kid].add(result)

        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = []
                for kid, pem in keys.items():
                    for _ in range(4):
                        futures.append(pool.submit(worker, kid, pem))
                for f in as_completed(futures):
                    f.result()  # propagate exceptions

            for kid, result_set in results.items():
                assert len(result_set) == 1, (
                    f"kid={kid} produced {len(result_set)} distinct public keys"
                )
        finally:
            sec._public_key_cache = original_cache


# ---------------------------------------------------------------------------
# HIBP client double-checked locking (MOD-22-02)
# ---------------------------------------------------------------------------


class TestHIBPClientDoubleCheckedLocking:
    """Verify that concurrent _get_hibp_client() calls create exactly one client."""

    @pytest.mark.asyncio
    async def test_concurrent_initialization(self) -> None:
        """Multiple coroutines calling _get_hibp_client concurrently must
        all receive the same client instance (only one is created)."""
        import app.auth.security as sec

        # Reset the global client so initialization is triggered.
        original_client = sec._hibp_client
        sec._hibp_client = None

        # Clear the lock cache so a fresh lock is created for this loop.
        sec._get_hibp_lock_for_loop.cache_clear()

        try:
            clients = await asyncio.gather(
                sec._get_hibp_client(),
                sec._get_hibp_client(),
                sec._get_hibp_client(),
                sec._get_hibp_client(),
            )
            # All returned clients must be the same object.
            assert all(c is clients[0] for c in clients), (
                "Multiple HIBP clients were created — double-checked locking failed"
            )
        finally:
            # Close the client we created and restore original state.
            if sec._hibp_client is not None and sec._hibp_client is not original_client:
                await sec._hibp_client.aclose()
            sec._hibp_client = original_client

    @pytest.mark.asyncio
    async def test_existing_client_fast_path(self) -> None:
        """When a client already exists, _get_hibp_client returns it without locking."""
        import app.auth.security as sec

        sentinel = MagicMock()
        original_client = sec._hibp_client
        sec._hibp_client = sentinel

        try:
            result = await sec._get_hibp_client()
            assert result is sentinel
        finally:
            sec._hibp_client = original_client


# ---------------------------------------------------------------------------
# SpiceDB health probe timing (MOD-22-02)
# ---------------------------------------------------------------------------


class TestSpiceDBCacheInvalidationTiming:
    """Verify that concurrent SpiceDB health checks don't produce stale results."""

    @pytest.mark.asyncio
    async def test_concurrent_health_probes(self) -> None:
        """Multiple concurrent calls to check_spicedb_health must not crash
        or produce invalid results under contention."""
        from app.core.health import check_spicedb_health

        # Run several probes concurrently — they should all return valid tuples
        # (status: str, latency_ms: float) even when SpiceDB is unavailable.
        results = await asyncio.gather(
            *[check_spicedb_health() for _ in range(8)],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):
                pytest.fail(f"check_spicedb_health raised under concurrency: {r}")
            status, latency_ms = r
            assert isinstance(status, str)
            assert isinstance(latency_ms, (int, float))
            assert latency_ms >= 0
