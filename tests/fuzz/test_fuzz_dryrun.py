"""Atheris fuzzing target for the rust_ext FFI module.

Enforces FFI stability and bounds safety by fuzzing input parsing under the Atheris engine.
On Windows (where Atheris is not supported), this test skips gracefully.
On Linux (CI), it executes a dry-run (1 iteration) via pytest.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

try:
    import atheris
except (ImportError, RuntimeError):
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
    # libFuzzer exits its process when the run budget is exhausted. Calling it
    # inside pytest silently terminates a serial run or kills an xdist worker.
    # Keep the real engine/FFI check, but contain its lifecycle in a child.
    result = subprocess.run(  # noqa: S603 - fixed test target/current interpreter
        [sys.executable, str(Path(__file__).resolve()), "--atheris-dry-run"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ATHERIS_DRY_RUN_INPUT" in result.stdout


@pytest.mark.parametrize(
    ("returncode", "stdout"), [(1, "ATHERIS_DRY_RUN_INPUT"), (0, "")]
)
def test_dryrun_rejects_failed_or_unexecuted_child(
    monkeypatch: pytest.MonkeyPatch, returncode: int, stdout: str
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=returncode, stdout=stdout, stderr=""
        ),
    )
    with pytest.raises(AssertionError):
        test_atheris_fuzz_dryrun()


def _run_atheris_dryrun() -> None:
    """Run the native engine only in its dedicated interpreter process."""

    def FuzzOneInput(input_bytes: bytes) -> None:
        # Flush before entering native code, whose process exit bypasses Python
        # stream cleanup. The parent verifies the target actually ran.
        print("ATHERIS_DRY_RUN_INPUT", flush=True)
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

    atheris.Setup([sys.argv[0], "-runs=1"], FuzzOneInput)
    atheris.Fuzz()


if __name__ == "__main__" and sys.argv[1:] == ["--atheris-dry-run"]:
    _run_atheris_dryrun()
