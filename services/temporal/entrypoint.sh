#!/bin/sh
# Wave 144 SW2 NEW (z) #17 — Temporal v1.30.2 plain server does NOT do
# env-var substitution in YAML config (unlike auto-setup which renders via
# envsubst inside its own entrypoint). The mounted services/temporal/config.yaml
# contains `${POSTGRES_USER}` + `${POSTGRES_PWD}` literal placeholders that
# Temporal's config loader passes straight into the postgres connection URL,
# resulting in `parse "postgres://${POSTGRES_USER}:%24%7BPOSTGRES_PWD%7D@...":
# net/url: invalid userinfo` at startup.
#
# This entrypoint does the substitution via `sed` (envsubst is NOT in the
# image — verified via `which envsubst` → empty; only sed at /bin/sed),
# writes the rendered file to /tmp/docker.yaml (writable, ephemeral),
# then exec's temporal-server with --root /tmp --config . --env docker
# so it finds the rendered docker.yaml there.
#
# BIND_ON_IP defaults to all interfaces because Compose attaches Temporal to
# multiple networks. Membership still needs one concrete advertised address,
# which is resolved independently below.

set -eu
# shellcheck disable=SC3040
set -o pipefail 2>/dev/null || true

# Render config.yaml with env-var substitution.
# Both POSTGRES_USER + POSTGRES_PWD are required (provided by docker-compose
# environment: block on the temporal service).
: "${POSTGRES_USER:?POSTGRES_USER env var required}"
: "${POSTGRES_PWD:?POSTGRES_PWD env var required}"

# Resolve container's bridge-network IP for membership broadcast.
BROADCAST_ADDRESS="$(getent hosts "$(hostname)" | awk '{print $1;}')"
: "${BIND_ON_IP:=0.0.0.0}"
export BIND_ON_IP BROADCAST_ADDRESS
: "${TEMPORAL_BROADCAST_ADDRESS:=${BROADCAST_ADDRESS}}"
export TEMPORAL_BROADCAST_ADDRESS

sed \
  -e "s|\${POSTGRES_USER}|${POSTGRES_USER}|g" \
  -e "s|\${POSTGRES_PWD}|${POSTGRES_PWD}|g" \
  -e "s|\${BROADCAST_ADDRESS}|${BROADCAST_ADDRESS}|g" \
  /etc/temporal/config/docker.yaml > /tmp/docker.yaml

# Start temporal-server reading from the rendered /tmp/docker.yaml.
# --root /tmp + --config . + --env docker → temporal-server reads /tmp/docker.yaml.
exec temporal-server --allow-no-auth --root /tmp --config . --env docker start
