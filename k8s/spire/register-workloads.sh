#!/usr/bin/env bash
set -euo pipefail

# Plan only. Supply a reviewed Helm render and an already-attested concrete
# parent ID; the former guessed cluster prefix is not a valid agent identity.
# This wrapper neither executes kubectl nor creates/updates SPIRE entries.
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python "${ROOT}/scripts/plan_spire_registration.py" "$@"
