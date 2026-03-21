#!/bin/sh
# scripts/garage-init.sh
# MOD-W8-01 (audit 2026-03-15): Idempotent bootstrap for a single-node Garage cluster.
#
# Runs once as a docker-compose init container after the 'garage' service reports
# healthy.  Safe to re-run on container restart — every command uses || true.
#
# Required env vars (injected by docker-compose):
#   GARAGE_RPC_SECRET    — must match the garage service
#   MINIO_ROOT_USER      — reused as the S3 access key ID (backward-compat)
#   MINIO_ROOT_PASSWORD  — reused as the S3 secret access key
#
# The MINIO_ROOT_USER / MINIO_ROOT_PASSWORD values are imported unchanged so
# that all existing MINIO_ACCESS_KEY / MINIO_SECRET_KEY references in backend
# and file-processor services continue to work without modification.

set -eu

GARAGE="garage -c /etc/garage.toml"

echo "[garage-init] Garage is ready (health check passed by depends_on)."

# ── Cluster layout ──────────────────────────────────────────────────────────
# In a single-node cluster every node must be assigned a zone and capacity
# before Garage will accept any S3 requests.  The layout is stored in the
# metadata database and persists across restarts; applying it twice is harmless.

echo "[garage-init] Reading node ID..."
NODE_ID=$(${GARAGE} node list --json 2>/dev/null \
    | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "${NODE_ID}" ]; then
    echo "[garage-init] ERROR: could not retrieve node ID from 'garage node list'."
    exit 1
fi
echo "[garage-init] Node ID: ${NODE_ID}"

echo "[garage-init] Assigning layout (zone=dc1, capacity=1G)..."
${GARAGE} layout assign "${NODE_ID}" --zone dc1 --capacity 1G 2>/dev/null || true

echo "[garage-init] Applying layout version 1..."
${GARAGE} layout apply --version 1 2>/dev/null || true

# ── Access key ──────────────────────────────────────────────────────────────
# Import the existing credentials so downstream services need no env-var changes.
echo "[garage-init] Importing S3 access key (id=${MINIO_ROOT_USER})..."
${GARAGE} key import \
    --key-id     "${MINIO_ROOT_USER}" \
    --key-secret "${MINIO_ROOT_PASSWORD}" \
    -n admin 2>/dev/null || true

# ── Bucket ───────────────────────────────────────────────────────────────────
echo "[garage-init] Creating bucket 'uploads'..."
${GARAGE} bucket create uploads 2>/dev/null || true

echo "[garage-init] Granting read/write/owner permissions..."
${GARAGE} bucket allow uploads \
    --key   "${MINIO_ROOT_USER}" \
    --read --write --owner 2>/dev/null || true

echo "[garage-init] Garage initialisation complete."
