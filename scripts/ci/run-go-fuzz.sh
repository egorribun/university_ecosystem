#!/usr/bin/env bash
# Go exits successfully when -fuzz matches no target. Require an exact compiled
# target before spending the fuzz budget, and propagate every Go failure.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo 'Usage: run-go-fuzz.sh PACKAGE FUZZ_TARGET [GO_TEST_FLAGS...]' >&2
  exit 2
fi

package=$1
target=$2
shift 2
if [[ ! $target =~ ^Fuzz[A-Z][A-Za-z0-9_]*$ ]]; then
  echo "Invalid fuzz target: $target" >&2
  exit 2
fi

# Only smoke-budget and verbosity flags may follow the target. In particular,
# -fuzz, -list, -skip, -args or another package could undo the exact selection.
for flag in "$@"; do
  case "$flag" in
    -v|-fuzztime=*|-parallel=*|-timeout=*) ;;
    *) echo "Unsupported fuzz flag: $flag" >&2; exit 2 ;;
  esac
done

targets=$(go test "$package" "-list=^${target}$")
if ! grep -Fxq -- "$target" <<< "$targets"; then
  echo "Missing fuzz target $target in $package" >&2
  exit 1
fi

go test "$package" "-fuzz=^${target}$" "$@"
