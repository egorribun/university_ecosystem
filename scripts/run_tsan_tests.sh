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

# ── Prove that this runner actually fails on a race -------------------------
# A passing test suite is not evidence that TSan was loaded correctly. Compile
# and execute a tiny, intentionally racy program first; a zero exit status is
# treated as a fail-closed runner error. The canary stays outside Python so its
# report cannot be hidden by PyO3/CPython suppressions.
TSAN_CANARY_SOURCE="${REPO_ROOT}/tests/tsan_race_canary.c"
TSAN_CANARY_BIN="${TMPDIR:-/tmp}/university-ecosystem-tsan-canary-$$"
TSAN_CANARY_LOG="${TSAN_CANARY_BIN}.log"
TSAN_CC="${CC:-cc}"
if ! command -v "${TSAN_CC}" >/dev/null 2>&1; then
  echo "ERROR: C compiler '${TSAN_CC}' is required for the TSan race canary." >&2
  exit 1
fi
cleanup_tsan_canary() {
  rm -f -- "${TSAN_CANARY_BIN}" "${TSAN_CANARY_LOG}"
}
trap cleanup_tsan_canary EXIT
"${TSAN_CC}" -fsanitize=thread -fno-omit-frame-pointer -O1 -g \
  "${TSAN_CANARY_SOURCE}" -pthread -o "${TSAN_CANARY_BIN}"
set +e
TSAN_OPTIONS="halt_on_error=1:exitcode=66:report_signal_unsafe=0" \
  "${TSAN_CANARY_BIN}" >"${TSAN_CANARY_LOG}" 2>&1
TSAN_CANARY_EXIT=$?
set -e
if [[ "${TSAN_CANARY_EXIT}" -eq 0 ]]; then
  echo "ERROR: TSan race canary unexpectedly exited successfully." >&2
  cat "${TSAN_CANARY_LOG}"
  exit 1
fi
if ! grep -Eq "WARNING: ThreadSanitizer|ThreadSanitizer: data race" "${TSAN_CANARY_LOG}"; then
  echo "ERROR: TSan race canary failed without a recognizable TSan report." >&2
  cat "${TSAN_CANARY_LOG}"
  exit 1
fi
echo "==> [TSan] Race canary correctly failed with a data-race report."

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
TSAN_LOG_PREFIX="${REPO_ROOT}/tsan-report"
# Never let a report left by an earlier invocation influence this run.  The
# prefix is repository-local and deliberately explicit so cleanup cannot touch
# unrelated files.
rm -f -- "${TSAN_LOG_PREFIX}".*

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "ERROR: Expected the uv-managed Python environment at '${PYTHON_BIN}'."
  echo "       Run 'uv sync --group dev' before running the TSan suite."
  exit 1
fi

set +e
LD_PRELOAD="${TSAN_LIB}" \
TSAN_OPTIONS="suppressions=${TSAN_SUPPRESSIONS_FILE}:halt_on_error=0:second_deadlock_stack=0:print_suppressions=1:verbosity=1:log_path=${TSAN_LOG_PREFIX}" \
  "${PYTHON_BIN}" -m pytest \
    tests/test_smoke_rust_audit.py \
    tests/test_smoke_rust_partitions.py \
    tests/test_property_based.py \
    tests/test_content_processing.py \
    tests/test_smoke_pyo3_ext.py \
    -v \
    --tb=short
TEST_EXIT_CODE=$?
set -e

TSAN_UNSUPPRESSED=0
shopt -s nullglob
for report in "${TSAN_LOG_PREFIX}".*; do
  if [[ -f "${report}" ]]; then
    cat "${report}"
    if grep -Eq "WARNING: ThreadSanitizer|ThreadSanitizer: data race|ThreadSanitizer: heap-use-after-free" "${report}"; then
      TSAN_UNSUPPRESSED=1
    fi
  fi
done

if [[ "${TSAN_UNSUPPRESSED}" -ne 0 ]]; then
  echo "ERROR: TSan reported an unsuppressed race or memory error." >&2
  exit 1
fi

if [[ "${TEST_EXIT_CODE}" -ne 0 ]]; then
  exit "${TEST_EXIT_CODE}"
fi

echo "==> [TSan] All FFI tests passed — no data races detected."
