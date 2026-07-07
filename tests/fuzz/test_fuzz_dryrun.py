"""Atheris fuzzing target for the rust_ext FFI module.

Enforces FFI stability and bounds safety by fuzzing input parsing under the Atheris engine.
On Windows (where Atheris is not supported), this test skips gracefully.
On Linux (CI), it executes a dry-run (1 iteration) via pytest.
"""

from __future__ import annotations

import sys

import pytest

try:
    import atheris
except ImportError:
    atheris = None

try:
    import rust_ext
except ImportError:
    rust_ext = None


@pytest.mark.skipif(
    atheris is None or rust_ext is None,
    reason="Atheris and/or rust_ext are not available (expected on Windows/non-FFI environments)",
)
def test_atheris_fuzz_dryrun() -> None:
    """Run exactly 1 iteration of the Atheris fuzzer target to verify integration."""

    def FuzzOneInput(input_bytes: bytes) -> None:
        fdp = atheris.FuzzedDataProvider(input_bytes)

        # Fuzz verify_audit_signature
        sig = fdp.ConsumeUnicodeNoSurrogates(128)
        payload = fdp.ConsumeUnicodeNoSurrogates(1024)

        try:
            rust_ext.verify_audit_signature(["key1", "key2"], payload, sig)
        except (TypeError, ValueError):
            pass

        # Fuzz is_partition_expired
        partition_name = fdp.ConsumeUnicodeNoSurrogates(64)
        table_name = fdp.ConsumeUnicodeNoSurrogates(64)
        retention_days = fdp.ConsumeIntInRange(-1000, 10000)

        try:
            rust_ext.is_partition_expired(partition_name, table_name, retention_days)
        except (TypeError, ValueError):
            pass

    # Configure Atheris to run for exactly 1 iteration for the dry-run gate
    # We pass '-runs=1' to the fuzzer arguments
    original_argv = sys.argv
    sys.argv = [sys.argv[0], "-runs=1"]
    try:
        # Register the instrumentation and target
        atheris.Setup(sys.argv, FuzzOneInput)
        atheris.Fuzz()
    finally:
        sys.argv = original_argv
