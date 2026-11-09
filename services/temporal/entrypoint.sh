#!/bin/sh
# Wave 144 SW2 NEW (z) #17 — Temporal v1.30.7 plain server does NOT do
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
# The public frontend binds all interfaces (config.yaml) because Compose attaches
# Temporal to multiple networks. The internal services bind 127.0.0.1 and
# membership advertises 127.0.0.1, so no container address lookup is needed.

set -eu
# shellcheck disable=SC3040
if (set -o pipefail) 2>/dev/null; then
  set -o pipefail
fi

# Render config.yaml with env-var substitution.
# Both POSTGRES_USER + POSTGRES_PWD are required (provided by docker-compose
# environment: block on the temporal service).
: "${POSTGRES_USER:?POSTGRES_USER env var required}"
: "${POSTGRES_PWD:?POSTGRES_PWD env var required}"
# The sed renderer below treats `&` as the matched text, `|` as the delimiter and
# `\` as an escape, and the config quotes these values, so the same character
# guard as TEMPORAL_JWKS_URL applies. grep reads line by line, so a line break is
# refused separately. Messages name the variable, never its value.
LINE_BREAK='
'
case "${POSTGRES_USER}" in
  *"${LINE_BREAK}"*)
    echo "POSTGRES_USER contains characters the config renderer does not accept" >&2
    exit 1
    ;;
esac
case "${POSTGRES_PWD}" in
  *"${LINE_BREAK}"*)
    echo "POSTGRES_PWD contains characters the config renderer does not accept" >&2
    exit 1
    ;;
esac
if printf '%s' "${POSTGRES_USER}" | grep -q '[][|&\\"'"'"' ]'; then
  echo "POSTGRES_USER contains characters the config renderer does not accept" >&2
  exit 1
fi
if printf '%s' "${POSTGRES_PWD}" | grep -q '[][|&\\"'"'"' ]'; then
  echo "POSTGRES_PWD contains characters the config renderer does not accept" >&2
  exit 1
fi

# AUD-506: JWT signing keys must be fetched over TLS. The claim mapper trusts
# whatever keys this endpoint returns, so plain HTTP would let a network
# attacker mint tokens. Fail closed when the endpoint is missing, not https, or
# contains characters the sed renderer below would misinterpret.
: "${TEMPORAL_JWKS_URL:?TEMPORAL_JWKS_URL must be an https JWKS endpoint}"
case "${TEMPORAL_JWKS_URL}" in
  https://?*) ;;
  *)
    echo "TEMPORAL_JWKS_URL must use the https scheme" >&2
    exit 1
    ;;
esac
if printf '%s' "${TEMPORAL_JWKS_URL}" | grep -q '[][|&\\"'"'"' ]'; then
  echo "TEMPORAL_JWKS_URL contains characters the config renderer does not accept" >&2
  exit 1
fi

# Single-container topology. The worker scanner's system client authenticates
# through internal-frontend, which is defined only on 127.0.0.1 (see config.yaml).
# Every service must be listed here, or the scanner crash-loops. Membership
# advertises 127.0.0.1 (fixed in config.yaml), so the list is checked exactly.
EXPECTED_TEMPORAL_SERVICES="frontend,history,matching,worker,internal-frontend"
: "${TEMPORAL_SERVICES:?TEMPORAL_SERVICES env var required}"
if [ "${TEMPORAL_SERVICES}" != "${EXPECTED_TEMPORAL_SERVICES}" ]; then
  echo "TEMPORAL_SERVICES must be ${EXPECTED_TEMPORAL_SERVICES}" >&2
  exit 1
fi
export TEMPORAL_SERVICES

# AUD-506: the JWKS listener presents a certificate from Caddy's internal CA. Compose
# copies only that public root into a read-only mount, so this process never sees
# the CA private key. Wait for the root, then trust it alongside the system roots.
# Go's crypto/x509 on Linux reads SSL_CERT_FILE to choose the root store.
TEMPORAL_JWKS_CA_FILE="${TEMPORAL_JWKS_CA_FILE:-/etc/temporal/jwks-ca/root.crt}"
jwks_ca_wait=0
until [ -s "${TEMPORAL_JWKS_CA_FILE}" ]; do
  jwks_ca_wait=$((jwks_ca_wait + 1))
  if [ "${jwks_ca_wait}" -gt 120 ]; then
    echo "JWKS trust anchor ${TEMPORAL_JWKS_CA_FILE} was not provided" >&2
    exit 1
  fi
  sleep 1
done
{
  if [ -r /etc/ssl/certs/ca-certificates.crt ]; then
    cat /etc/ssl/certs/ca-certificates.crt
  fi
  cat "${TEMPORAL_JWKS_CA_FILE}"
} > /tmp/temporal-jwks-ca-bundle.pem
export SSL_CERT_FILE=/tmp/temporal-jwks-ca-bundle.pem

: "${BIND_ON_IP:=0.0.0.0}"
export BIND_ON_IP

sed \
  -e "s|\${POSTGRES_USER}|${POSTGRES_USER}|g" \
  -e "s|\${POSTGRES_PWD}|${POSTGRES_PWD}|g" \
  -e "s|\${TEMPORAL_JWKS_URL}|${TEMPORAL_JWKS_URL}|g" \
  /etc/temporal/config/docker.yaml > /tmp/docker.yaml

# Start temporal-server reading from the rendered /tmp/docker.yaml.
# --root /tmp + --config . + --env docker → temporal-server reads /tmp/docker.yaml.
# TEMPORAL_SERVICES (exported above) selects the services to run in this process.
# The shared Compose path must retain Temporal's configured authentication
# boundary.  In particular, do not pass Temporal's no-authorizer CLI switch
# here: that option would also affect
# the production-like Compose stack.  The mounted config's JWT claim mapper
# remains responsible for authenticating service calls.
exec temporal-server --root /tmp --config . --env docker start
