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

for attempt in 1 2 3; do
  if npx playwright install --with-deps "${browsers[@]}"; then
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
