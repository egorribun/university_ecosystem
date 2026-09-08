#!/usr/bin/env bash
# OSS-Fuzz build script for the pyo3-sanitizer libFuzzer targets.
#
# The OSS-Fuzz builder invokes this script with SRC and OUT set.  Keep the
# manifest explicit: the repository intentionally has no root Cargo workspace,
# so running cargo-fuzz from the checkout root would be a silent no-op.
set -euo pipefail

: "${SRC:?SRC must point to the OSS-Fuzz source root}"
: "${OUT:?OUT must point to the OSS-Fuzz output directory}"

REPOSITORY_ROOT="${SRC}/university_ecosystem"
FUZZ_ROOT="${REPOSITORY_ROOT}/crates/pyo3-sanitizer/fuzz"
test -d "${FUZZ_ROOT}"
test -f "${FUZZ_ROOT}/Cargo.toml"

cd "${FUZZ_ROOT}"

mapfile -t fuzzers < <(cargo fuzz list | awk 'NF { print $1 }' | sort)
if (( ${#fuzzers[@]} == 0 )); then
    echo "ERROR: cargo-fuzz reported no targets for ${FUZZ_ROOT}" >&2
    exit 1
fi

cargo fuzz build --release

for fuzzer in "${fuzzers[@]}"; do
    binary="${FUZZ_ROOT}/target/x86_64-unknown-linux-gnu/release/${fuzzer}"
    if [[ ! -x "${binary}" ]]; then
        echo "ERROR: cargo-fuzz did not produce executable ${binary}" >&2
        exit 1
    fi
    install -m 0755 "${binary}" "${OUT}/${fuzzer}"
done

if [[ -z "$(find "${OUT}" -maxdepth 1 -type f -perm -u+x -print -quit)" ]]; then
    echo "ERROR: OSS-Fuzz output directory is empty after cargo-fuzz build" >&2
    exit 1
fi
