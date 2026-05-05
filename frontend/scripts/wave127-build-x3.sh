#!/usr/bin/env bash
# Wave 127 SW7 — build × 3 reproducibility check.
# vite-plugin-pwa injectManifest hangs post-prerender on Windows (W126 polish #3).
# Workaround: launch build in background, watch for dist/server/server.js (signals
# vite + prerender done), kill the npm chain, then run build:shell standalone.

run_build() {
  local n=$1
  rm -rf dist
  echo "=== BUILD ${n} ==="
  npm run build > /tmp/build${n}.log 2>&1 &
  local BUILD_PID=$!
  # Wait up to 90s for dist/server/server.js to appear
  for i in $(seq 1 90); do
    if [ -f dist/server/server.js ]; then break; fi
    sleep 1
  done
  # Wait briefly for vite-plugin-pwa to start hanging, then kill
  sleep 3
  kill -9 $BUILD_PID 2>/dev/null
  # Kill any orphan node child processes
  ps -ef | grep -E "node.*(vite|build)" | grep -v grep | awk '{print $2}' | xargs -r kill -9 2>/dev/null
  sleep 1
  if [ ! -f dist/server/server.js ]; then
    echo "Build ${n}: FAILED — dist/server/server.js missing"
    tail -20 /tmp/build${n}.log
    return 1
  fi
  npm run build:shell > /tmp/build${n}_shell.log 2>&1
  local HASH=$(ls dist/client/assets/index-*.js 2>/dev/null | head -1 | xargs basename 2>/dev/null)
  local SIZE=$(stat -c %s dist/client/assets/$HASH 2>/dev/null || echo "?")
  local SHELL=$(stat -c %s dist/client/_shell.html 2>/dev/null || echo "?")
  echo "Build ${n}: $HASH ($SIZE bytes) | _shell.html ($SHELL bytes)"
}

run_build 1
run_build 2
run_build 3

echo ""
echo "=== W126 BASELINE: index-B9t65bNz.js (137813 bytes) | _shell.html (~10448) ==="
