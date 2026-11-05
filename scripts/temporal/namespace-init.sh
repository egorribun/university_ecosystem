#!/bin/sh
# PRIVATE REVIEW CANDIDATE. Must share Temporal's network namespace.
set -eu

profile=/run/temporal-bootstrap/profile.toml
worker_key=/run/temporal-worker/token
worker_profile=/run/temporal-bootstrap-runtime/worker.toml
if [ "$(id -u)" != 1000 ] || [ "$(id -g)" != 1000 ] || [ ! -s "$worker_key" ] || [ ! -r "$worker_key" ]; then
  echo '[temporal-namespace-init] worker credential unavailable; use the launcher' >&2
  exit 1
fi
if [ ! -d /run/temporal-bootstrap-runtime ] || [ ! -w /run/temporal-bootstrap-runtime ]; then
  echo '[temporal-namespace-init] private runtime directory unavailable' >&2
  exit 1
fi
set +x
umask 077
worker_length=$(wc -c < "$worker_key")
if [ "$worker_length" -gt 4096 ]; then
  echo '[temporal-namespace-init] worker credential is invalid' >&2
  exit 1
fi
worker_token=$(cat "$worker_key")
case "$worker_token" in
  ''|*[!A-Za-z0-9._-]*) echo '[temporal-namespace-init] worker credential is invalid' >&2; exit 1 ;;
esac
trap 'rm -f "$worker_profile"' 0
trap 'exit 1' HUP INT TERM
printf "[profile.default]\naddress = '127.0.0.1:7233'\nnamespace = 'default'\napi_key = '%s'\n[profile.default.tls]\ndisabled = true\n" "$worker_token" > "$worker_profile"
unset worker_token

# No inherited environment may redirect the profile, address, TLS, or API key.
# The pinned image puts the CLI at /usr/local/bin/temporal.
run_temporal() {
  env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp temporal "$@" >/dev/null 2>&1
}

# Suppress CLI diagnostics, which are not a guaranteed secret-safe API. Flags
# identify only fixed paths/options. All RPCs stay on the shared loopback.
ready=false
# Try existing least-privileged credentials first. With no admin profile, retry
# across the 60s JWKS refresh; with a fresh admin profile, proceed immediately.
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24; do
  if run_temporal operator namespace describe --config-file "$worker_profile" --address 127.0.0.1:7233 --tls=false --command-timeout 2s --namespace default; then
    exit 0
  fi
  if [ -s "$profile" ]; then break; fi
  sleep 3
done
if [ ! -s "$profile" ] || [ ! -r "$profile" ]; then
  echo '[temporal-namespace-init] namespace could not be verified; use the launcher' >&2
  exit 1
fi

# 24 * (2s command + 3s delay) = at most 120s, spanning a 60s JWKS refresh.
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24; do
  if run_temporal operator cluster health --config-file "$profile" --address 127.0.0.1:7233 --tls=false --command-timeout 2s; then
    ready=true
    break
  fi
  sleep 3
done
if [ "$ready" != true ]; then
  echo '[temporal-namespace-init] authenticated health check failed' >&2
  exit 1
fi

# 12 * (3 commands * 2s + 2s delay) = at most 96s. Success always requires
# an authenticated describe; a failed create alone is never treated as success.
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
  if run_temporal operator namespace describe --config-file "$profile" --address 127.0.0.1:7233 --tls=false --command-timeout 2s --namespace default; then
    exit 0
  fi
  if run_temporal operator namespace create --config-file "$profile" --address 127.0.0.1:7233 --tls=false --command-timeout 2s --namespace default --retention 24h; then
    :
  fi
  if run_temporal operator namespace describe --config-file "$profile" --address 127.0.0.1:7233 --tls=false --command-timeout 2s --namespace default; then
    exit 0
  fi
  sleep 2
done
echo '[temporal-namespace-init] namespace initialization could not be verified' >&2
exit 1
