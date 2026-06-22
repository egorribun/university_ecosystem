#!/bin/bash
# scripts/run-docker-visual-tests.sh
# Runs Playwright visual regression tests inside the official Playwright Docker container
# to update or verify Linux-based screenshots.

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

echo "Starting Playwright container (v1.58.2-noble) to run visual E2E tests..."
docker run --rm -it \
  -v "$ROOT:/work" \
  -w /work/frontend \
  mcr.microsoft.com/playwright:v1.58.2-noble \
  npx playwright test tests/e2e/visual.spec.ts --project=chromium $UPDATE_FLAG

echo "Visual tests complete."
