#!/usr/bin/env bash
# scripts/run_tsan_tests.sh — Run Rust FFI tests under ThreadSanitizer (TSan).
#
# WHY: PyO3 extensions cross the Rust/Python FFI boundary. Data races and threading issues
# in Rust code are hard to detect and debug. ThreadSanitizer instruments memory accesses
# and synchronization primitives to detect data races in multithreaded environments.
#
# USAGE:
#   bash scripts/run_tsan_tests.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUST_EXT_DIR="${REPO_ROOT}/native/rust_ext"

echo "==> [TSan] Repository root: ${REPO_ROOT}"
echo "==> [TSan] Rust extension:  ${RUST_EXT_DIR}"

# ── Ensure Rust nightly + rust-src component ─────────────────────────
echo "==> [TSan] Installing Rust nightly toolchain and rust-src component..."
rustup toolchain install nightly --component rust-src --allow-downgrade --no-self-update
rustup override set nightly --path "${RUST_EXT_DIR}"

# ── Detect target triple ─────────────────────────────────────────────
echo "==> [TSan] Detecting target triple..."
RUST_SYSROOT="$(rustup run nightly rustc --print sysroot)"
HOST_TRIPLE="$(rustup run nightly rustc -vV | grep "^host:" | awk '{print $2}')"

echo "==> [TSan] Rebuilding rust_ext under TSan (nightly, force-reinstall)..."
(
  cd "${RUST_EXT_DIR}"
  unset RUSTFLAGS
  export RUSTUP_TOOLCHAIN=nightly
  TRIPLE_UPPER="$(echo "${HOST_TRIPLE}" | tr '-' '_' | tr '[:lower:]' '[:upper:]')"
  export "CARGO_TARGET_${TRIPLE_UPPER}_RUSTFLAGS=-Zsanitizer=thread"
  uv run maturin develop --release --target "${HOST_TRIPLE}" -Zbuild-std=std,panic_abort
)

echo "==> [TSan] Rebuilding pyo3-sanitizer under TSan (nightly, force-reinstall)..."
(
  cd "${REPO_ROOT}/crates/pyo3-sanitizer"
  unset RUSTFLAGS
  export RUSTUP_TOOLCHAIN=nightly
  TRIPLE_UPPER="$(echo "${HOST_TRIPLE}" | tr '-' '_' | tr '[:lower:]' '[:upper:]')"
  export "CARGO_TARGET_${TRIPLE_UPPER}_RUSTFLAGS=-Zsanitizer=thread"
  uv run maturin develop --release --target "${HOST_TRIPLE}" -Zbuild-std=std,panic_abort
)

# ── Locate TSan runtime shared library ───────────────────────────────
echo "==> [TSan] Locating TSan runtime library..."
TSAN_LIB=""
for candidate in \
    "${RUST_SYSROOT}/lib/rustlib/${HOST_TRIPLE}/lib/libclang_rt.tsan-${HOST_TRIPLE%%-*}.so" \
    "${RUST_SYSROOT}/lib/rustlib/${HOST_TRIPLE}/lib/libclang_rt.tsan.so" \
    "$(ldconfig -p 2>/dev/null | grep "libtsan.so" | head -1 | awk '{print $4}')"; do
  if [[ -f "${candidate}" ]]; then
    TSAN_LIB="${candidate}"
    break
  fi
done

if [[ -z "${TSAN_LIB}" ]]; then
  echo "ERROR: Could not locate TSan runtime library under Rust sysroot '${RUST_SYSROOT}'."
  echo "       Try: rustup component add llvm-tools --toolchain nightly"
  exit 1
fi

echo "==> [TSan] Using TSan runtime: ${TSAN_LIB}"

# ── Run tests under TSan ─────────────────────────────────────────────
echo "==> [TSan] Running FFI tests under TSan..."

# WHY suppressions: libuv (CPython's asyncio backend) and tokio's mio waker
# use an intentional self-pipe design where two threads share opposite ends
# of a pipe fd.  TSan flags these as races in memcpy, but they are safe by
# POSIX design.  The suppressions file limits the report to actual races in
# our Rust extension code.  abort_on_error is dropped because the TSan
# deadlock-detector overflows when libuv holds >64 internal locks — that
# overflow causes a CHECK-fail that kills the process before tests finish.
TSAN_SUPPRESSIONS_FILE="${REPO_ROOT}/tests/tsan_suppressions.txt"
PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "ERROR: Expected the uv-managed Python environment at '${PYTHON_BIN}'."
  echo "       Run 'uv sync --group dev' before running the TSan suite."
  exit 1
fi

LD_PRELOAD="${TSAN_LIB}" \
TSAN_OPTIONS="suppressions=${TSAN_SUPPRESSIONS_FILE}:halt_on_error=0:second_deadlock_stack=0:print_suppressions=1:verbosity=1" \
  "${PYTHON_BIN}" -m pytest \
    tests/test_smoke_rust_audit.py \
    tests/test_smoke_rust_partitions.py \
    tests/test_property_based.py \
    tests/test_content_processing.py \
    tests/test_smoke_pyo3_ext.py \
    -v \
    --tb=short

echo "==> [TSan] All FFI tests passed — no data races detected."
