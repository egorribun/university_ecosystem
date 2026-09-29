#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -lt 1 ]]; then
  echo "::error::At least one Playwright browser is required." >&2
  exit 2
fi

browsers=()
for browser in "$@"; do
  case "$browser" in
    mobile-webkit)
      browsers+=(webkit)
      ;;
    chromium|chrome|firefox|webkit)
      browsers+=("$browser")
      ;;
    *)
      echo "::error::Unsupported Playwright browser: $browser" >&2
      exit 2
      ;;
  esac
done

# Hosted images can retain an out-of-sync optional Chrome apt index.  Disable
# only the known optional source files; the runner's standard repositories and
# Playwright's own dependency resolver remain untouched.
for source in \
  /etc/apt/sources.list.d/google-chrome.list \
  /etc/apt/sources.list.d/google-chrome.sources; do
  if [[ -f "$source" ]]; then
    sudo mv "$source" "$source.disabled"
  fi
done

# GitHub-hosted Ubuntu runners normally contain the shared system libraries
# required by Playwright.  The reusable E2E workflow opts into a browser-only
# download to avoid repeating Playwright's apt bootstrap on every shard.  A
# dry-run dependency probe remains fail-closed: if any library is missing (or
# the probe cannot complete), fall back to the full --with-deps installation.
# Keep the dependency bootstrap as the default for local and self-hosted
# runners, where the host library inventory is not controlled by this repo.
skip_system_deps="${PLAYWRIGHT_SKIP_SYSTEM_DEPS:-0}"
case "$skip_system_deps" in
  1|true|TRUE)
    install_playwright() {
      if npx playwright install-deps --dry-run "${browsers[@]}"; then
        npx playwright install "${browsers[@]}"
      else
        echo "Playwright system dependency probe failed; using --with-deps fallback." >&2
        npx playwright install --with-deps "${browsers[@]}"
      fi
    }
    ;;
  0|false|FALSE|"")
    install_playwright() {
      npx playwright install --with-deps "${browsers[@]}"
    }
    ;;
  *)
    echo "::error::PLAYWRIGHT_SKIP_SYSTEM_DEPS must be 0/false or 1/true" >&2
    exit 2
    ;;
esac

for attempt in 1 2 3; do
  if install_playwright; then
    echo "Playwright browsers installed on attempt $attempt"
    exit 0
  fi
  if [[ "$attempt" -eq 3 ]]; then
    echo "::error::Playwright installation failed after 3 attempts" >&2
    exit 1
  fi
  echo "Playwright installation failed on attempt $attempt; retrying..." >&2
  sleep $((attempt * 10))
done
