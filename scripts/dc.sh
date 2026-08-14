#!/usr/bin/env sh
# scripts/dc.sh — Docker Compose wrapper that always resolves to the git repo
# root regardless of caller cwd.
#
# Mitigates W169 (z) #1: `docker compose -f docker-compose.full.yml ...` is
# path-sensitive. Bash cwd drift from `cd subdir && ...` chains caused silent
# failure during Wave 169 SW4 (compose exited 0 with no rebuild because the
# compose file was looked up relative to the drifted cwd `frontend/`). This
# wrapper ALWAYS resolves to the git repo root via `git rev-parse --show-toplevel`
# so cwd cannot drift the invocation.
#
# Usage examples:
#   bash scripts/dc.sh up -d --build frontend
#   bash scripts/dc.sh ps
#   bash scripts/dc.sh logs -f backend
#   bash scripts/dc.sh exec frontend sh -c 'ls -la /app/dist/client/assets'
#
# All arguments after the script name are passed transparently to
# `docker compose -f docker-compose.full.yml ...`.
#
# Cross-reference: CLAUDE.md ## Gotchas "Docker compose helper scripts" + the
# pre-existing W169 SW6-followup entry "`docker compose` exit code NOT a
# reliable success signal — cwd drift causes silent failure".

set -e

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$ROOT" ]; then
  echo "scripts/dc.sh: ERROR — not in a git repository. Aborting." >&2
  exit 1
fi

cd "$ROOT"
ENV_FILE="$ROOT/.env.docker"
if [ ! -f "$ENV_FILE" ]; then
  echo "scripts/dc.sh: ERROR — .env.docker is missing. Run ./start-docker.ps1 once to generate it." >&2
  exit 1
fi

exec docker compose -f docker-compose.full.yml --env-file "$ENV_FILE" "$@"
