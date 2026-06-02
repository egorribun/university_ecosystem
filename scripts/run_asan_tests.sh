#!/usr/bin/env bash
# scripts/run_asan_tests.sh — Run Rust FFI tests under AddressSanitizer + LeakSanitizer.
#
# WHY: PyO3 extensions cross the Rust/Python FFI boundary.  Memory errors and
# leaks in Rust code are invisible to Python's garbage collector and will not
# be caught by normal pytest runs.  ASan/LSan instruments every allocation and
# pointer dereference, making these classes of bugs fail loudly at test time
# rather than causing silent corruption in production.
#
# USAGE:
#   bash scripts/run_asan_tests.sh
#
# REQUIREMENTS:
#   - Linux (ASan runtime is not available on macOS/Windows without clang)
#   - Rust nightly toolchain (installed via rustup)
#   - uv Python package manager
#   - Python dev headers (for maturin to link against)
#
# ENVIRONMENT:
#   ASAN_LOG_PATH  — write ASan report to this file instead of stderr
#
# EXIT CODES:
#   0 — all tests passed, no memory errors detected
#   1 — test failure or memory error detected

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUST_EXT_DIR="${REPO_ROOT}/native/rust_ext"

echo "==> [ASan] Repository root: ${REPO_ROOT}"
echo "==> [ASan] Rust extension:  ${RUST_EXT_DIR}"

# ── Step 1: Ensure Rust nightly + rust-src component ─────────────────────────
#
# ASan in Rust requires -Zbuild-std which recompiles libstd with sanitizer
# support.  This requires the rust-src component.
echo "==> [ASan] Installing Rust nightly toolchain and rust-src component..."
rustup toolchain install nightly --component rust-src --allow-downgrade --no-self-update
rustup override set nightly --path "${RUST_EXT_DIR}"

# ── Step 2: Rebuild rust_ext with ASan instrumentation ───────────────────────
#
# RUSTFLAGS=-Zsanitizer=address instructs rustc to instrument every memory
# access.  We also pass -Zbuild-std=std,panic_abort so the sanitizer can
# trace through std internals without false positives.
#
# maturin develop builds a .so that is importable from the current Python env.
# We force-reinstall so that any previously cached non-instrumented build is
# replaced immediately.
echo "==> [ASan] Rebuilding rust_ext under ASan (nightly, force-reinstall)..."
(
  cd "${RUST_EXT_DIR}"
  RUSTUP_TOOLCHAIN=nightly \
  RUSTFLAGS="-Zsanitizer=address -Zbuild-std=std,panic_abort" \
    uv run maturin develop --release
)

# ── Step 3: Locate the ASan runtime shared library ───────────────────────────
#
# The ASan runtime must be LD_PRELOAD-ed when running Python because Python
# itself is not instrumented.  The library lives under the rustc sysroot and
# its exact path depends on the host architecture and Rust version.
echo "==> [ASan] Locating ASan runtime library..."

RUST_SYSROOT="$(rustup run nightly rustc --print sysroot)"
HOST_TRIPLE="$(rustup run nightly rustc -vV | grep "^host:" | awk '{print $2}')"

# Prefer libclang_rt.asan-<arch>.so (LLVM layout) then fall back to
# libclang_rt.asan.so and libasan.so (GCC layout).
ASAN_LIB=""
for candidate in \
    "${RUST_SYSROOT}/lib/rustlib/${HOST_TRIPLE}/lib/libclang_rt.asan-${HOST_TRIPLE%%-*}.so" \
    "${RUST_SYSROOT}/lib/rustlib/${HOST_TRIPLE}/lib/libclang_rt.asan.so" \
    "$(ldconfig -p 2>/dev/null | grep "libasan.so" | head -1 | awk '{print $4}')"; do
  if [[ -f "${candidate}" ]]; then
    ASAN_LIB="${candidate}"
    break
  fi
done

if [[ -z "${ASAN_LIB}" ]]; then
  echo "ERROR: Could not locate ASan runtime library under Rust sysroot '${RUST_SYSROOT}'."
  echo "       Try: rustup component add llvm-tools-preview --toolchain nightly"
  exit 1
fi

echo "==> [ASan] Using ASan runtime: ${ASAN_LIB}"

# ── Step 4: Run tests under ASan/LSan ────────────────────────────────────────
#
# ASAN_OPTIONS:
#   detect_leaks=1           — enable LeakSanitizer (LSan) integration
#   detect_odr_violation=0   — suppress false positives from Python's
#                              shared library symbol collisions
#   abort_on_error=1         — crash immediately on first error for CI clarity
#   log_path=...             — persist report to a file (optional, CI artifact)
#
# We target only the FFI smoke tests and property-based tests.  These exercise
# the Rust extension directly and are fast enough to run in a single CI job.
echo "==> [ASan] Running FFI tests under ASan/LSan..."

ASAN_LOG_PATH="${ASAN_LOG_PATH:-}"
ASAN_LOG_OPT=""
if [[ -n "${ASAN_LOG_PATH}" ]]; then
  ASAN_LOG_OPT="log_path=${ASAN_LOG_PATH}:"
fi

LD_PRELOAD="${ASAN_LIB}" \
ASAN_OPTIONS="${ASAN_LOG_OPT}detect_leaks=1:detect_odr_violation=0:abort_on_error=1" \
  uv run pytest \
    tests/test_smoke_rust_audit.py \
    tests/test_smoke_rust_partitions.py \
    tests/test_property_based.py \
    -v \
    --tb=short

echo "==> [ASan] All FFI tests passed — no memory errors or leaks detected."
