#!/bin/bash
# scripts/run-docker-visual-tests.sh
# Runs Playwright visual regression tests inside the official Playwright Docker container
# with Linux browser binaries. The selected suite currently has Windows-only
# baselines; an all-skipped run does not establish Linux visual acceptance.

set -e

UPDATE_FLAG=""
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --update|-u) UPDATE_FLAG="--update-snapshots" ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"

if ! command -v docker &> /dev/null; then
    echo "Error: docker is not installed or not in PATH."
    exit 1
fi

echo "Warning: the selected snapshot suite currently skips Linux; this command does not complete visual acceptance." >&2
echo "Starting Playwright container (v1.63.0-noble) to run visual E2E tests..."
docker run --rm -it \
  -v "$ROOT:/work" \
  -w /work/frontend \
  mcr.microsoft.com/playwright:v1.63.0-noble@sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27 \
  npx playwright test tests/e2e/visual.spec.ts --project=chromium $UPDATE_FLAG

echo "Visual command finished. Review the report for executed and skipped tests."
