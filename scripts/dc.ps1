# scripts/dc.ps1 - Docker Compose wrapper that always resolves to the git repo
# root regardless of caller cwd.
#
# Mitigates W169 (z) #1: `docker compose -f docker-compose.full.yml ...` is
# path-sensitive. PowerShell cwd drift from `Set-Location` (or `cd`) causes
# silent failure (compose exits 0 with no rebuild because the compose file is
# looked up relative to the drifted cwd). This wrapper ALWAYS resolves to the
# git repo root via `git rev-parse --show-toplevel` so cwd cannot drift the
# invocation.
#
# Usage examples:
#   pwsh scripts/dc.ps1 up -d --build frontend
#   pwsh scripts/dc.ps1 ps
#   pwsh scripts/dc.ps1 logs -f backend
#   pwsh scripts/dc.ps1 exec frontend sh -c 'ls -la /app/dist/client/assets'
#
# All arguments after the script name are forwarded transparently to
# `docker compose -f docker-compose.full.yml ...` via PowerShell @args splat.
#
# Cross-reference: CLAUDE.md ## Gotchas "Docker compose helper scripts" + the
# pre-existing W169 SW6-followup entry "`docker compose` exit code NOT a
# reliable success signal - cwd drift causes silent failure".

$ErrorActionPreference = "Stop"

$root = & git rev-parse --show-toplevel 2>$null
if (-not $root) {
  Write-Error "scripts/dc.ps1: ERROR - not in a git repository. Aborting."
  exit 1
}

# `git rev-parse --show-toplevel` emits a POSIX-style path on Windows
# (e.g. `C:/Users/.../university_ecosystem`). Convert to Windows-style for
# PowerShell `Set-Location`.
$root = $root -replace '/', '\'

Set-Location $root
& docker compose -f docker-compose.full.yml @args
exit $LASTEXITCODE
