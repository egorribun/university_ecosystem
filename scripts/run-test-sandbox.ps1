# scripts/run-test-sandbox.ps1 - reproducible local full-suite test sandbox.
#
# Brings up the four backing services (Postgres / Redis / NATS / MinIO) from
# docker-compose.sandbox.yml on isolated host ports, runs DB migrations, compiles
# the Rust FFI extension (maturin develop), and runs the full local test matrix:
# backend pytest+coverage, Go tests, Rust cargo test, frontend vitest.
#
# Mirrors scripts/dc.ps1: resolves to the git repo root via `git rev-parse
# --show-toplevel` so cwd drift cannot break the invocation.
#
# Usage:
#   pwsh scripts/run-test-sandbox.ps1                 # full run (infra + integration + all suites)
#   pwsh scripts/run-test-sandbox.ps1 -Filter backend # only the backend suite
#   pwsh scripts/run-test-sandbox.ps1 -Hermetic       # fast: no Docker, SQLite, unit-only
#   pwsh scripts/run-test-sandbox.ps1 -KeepUp         # leave the sandbox infra running afterwards
#
# Windows/Linux mitigations:
#   - Go `-race` needs gcc (absent on some Windows boxes per ADR-022). Detected;
#     dropped with a warning when missing (CI Linux always runs -race).
#   - pyvips (libvips) + clamd: the hermetic unit tests mock both; only the real
#     integration tier needs them. A warning is printed when they are absent.

[CmdletBinding()]
param(
  [ValidateSet("all", "backend", "go", "rust", "frontend")]
  [string]$Filter = "all",
  [switch]$Hermetic,   # skip Docker infra + integration tier (fast, SQLite, unit-only)
  [switch]$KeepUp      # leave the sandbox infra running after the run
)

$ErrorActionPreference = "Stop"

$root = & git rev-parse --show-toplevel 2>$null
if (-not $root) {
  Write-Error "run-test-sandbox.ps1: not in a git repository. Aborting."
  exit 1
}
$root = $root -replace '/', '\'
Set-Location $root

$compose = "docker-compose.sandbox.yml"
$worktreeHash = ([Convert]::ToHexString(
  [Security.Cryptography.SHA256]::HashData(
    [Text.Encoding]::UTF8.GetBytes($root)
  )
)).Substring(0, 12).ToLowerInvariant()
$composeProject = "ue-sandbox-$worktreeHash"
$useInfra = -not $Hermetic
$failed = [System.Collections.Generic.List[string]]::new()

function Invoke-Step {
  param([string]$Name, [scriptblock]$Block)
  Write-Host "`n=== $Name ===" -ForegroundColor Cyan
  try {
    & $Block
    if ($LASTEXITCODE -ne 0) {
      Write-Warning "${Name}: exit code $LASTEXITCODE"
      $script:failed.Add($Name)
    }
  } catch {
    Write-Warning "${Name}: $_"
    $script:failed.Add($Name)
  }
}

# -- Test-environment variables ----------------------------------------------
$env:ENVIRONMENT = "testing"
$env:SECRET_KEY = "test-secret-key-32-characters-long-entropy"  # pragma: allowlist secret
if ($useInfra) {
  # Point the backend at the sandbox infra (ports match docker-compose.sandbox.yml).
  $env:DATABASE_URL = "postgresql+asyncpg://test:test@localhost:55432/test"  # pragma: allowlist secret
  $env:RUN_INTEGRATION_TESTS = "1"
  $env:CACHE_REDIS_URL = "redis://localhost:16379/0"
  $env:RATE_LIMIT_STORAGE_URI = "redis://localhost:16379/1"
  $env:NATS_URL = "nats://localhost:54222"
  $env:AWS_ACCESS_KEY_ID = "minioadmin"
  $env:AWS_SECRET_ACCESS_KEY = "minioadmin"  # pragma: allowlist secret
  $env:S3_ENDPOINT_URL = "http://localhost:59000"
} else {
  # Hermetic: let conftest.py default to SQLite + fakeredis; no infra required.
  Remove-Item Env:\DATABASE_URL -ErrorAction SilentlyContinue
  Remove-Item Env:\RUN_INTEGRATION_TESTS -ErrorAction SilentlyContinue
}

# pyvips / clamd availability (informational - unit tests mock both).
if (-not (Get-Command vips -ErrorAction SilentlyContinue) -and -not $env:VIPS_HOME) {
  Write-Warning "libvips (pyvips) not detected on PATH/VIPS_HOME - real image-optimization integration paths will be skipped; unit tests mock pyvips."
}

try {
  if ($useInfra) {
    Invoke-Step "Sandbox infra up (Postgres/Redis/NATS/MinIO)" {
      docker compose --project-name $composeProject -f $compose up -d --wait
    }
  }

  if ($Filter -in @("all", "backend")) {
    if ($useInfra) {
      Invoke-Step "Alembic migrations (sandbox Postgres)" { uv run alembic upgrade head }
    }
    Invoke-Step "Compile Rust FFI extension (maturin develop)" {
      uv run maturin develop --manifest-path native/rust_ext/Cargo.toml
    }
    Invoke-Step "Backend pytest + coverage" {
      $previousDatabaseResetOptIn = $env:UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET
      try {
        if ($useInfra) {
          # This subprocess owns the disposable sandbox database. Keep the
          # destructive-reset capability scoped to pytest and restore the
          # caller's environment before any later tool runs.
          $env:UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET = "1"
          # The integration tier runs against the sandbox Postgres. Two test files
          # need a live gateway + Tempo (not part of the four backing services),
          # so they are skipped here; CI runs them in the full service mesh.
          uv run pytest tests/ --cov=app --cov-report=term-missing -q `
            --ignore=tests/integration/test_gateway_revocation.py `
            --ignore=tests/integration/test_trace_driven.py
        } else {
          uv run pytest tests/ --cov=app --cov-report=term-missing -q
        }
      } finally {
        if ($null -eq $previousDatabaseResetOptIn) {
          Remove-Item Env:\UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET -ErrorAction SilentlyContinue
        } else {
          $env:UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET = $previousDatabaseResetOptIn
        }
      }
    }
  }

  if ($Filter -in @("all", "rust")) {
    Invoke-Step "Rust cargo test (native/rust_ext)" {
      cargo test --manifest-path native/rust_ext/Cargo.toml
    }
  }

  if ($Filter -in @("all", "go")) {
    $hasGcc = [bool](Get-Command gcc -ErrorAction SilentlyContinue)
    if (-not $hasGcc) {
      Write-Warning "gcc not found - running Go tests WITHOUT -race (ADR-022; CI Linux runs -race)."
    }
    foreach ($svc in @("services/gateway", "services/file-processor", "services/ws-hub", "services/cmd/uni-cli")) {
      Invoke-Step "Go test ($svc)" {
        Push-Location $svc
        try {
          if ($hasGcc) { go test -race ./... } else { go test ./... }
        } finally {
          Pop-Location
        }
      }
    }
  }

  if ($Filter -in @("all", "frontend")) {
    Invoke-Step "Frontend vitest + coverage" {
      Push-Location frontend
      try { npm run test:ci } finally { Pop-Location }
    }
  }
} finally {
  if ($useInfra -and -not $KeepUp) {
    Write-Host "`n=== Sandbox infra down ===" -ForegroundColor Cyan
    docker compose --project-name $composeProject -f $compose down -v
  }
}

if ($failed.Count -gt 0) {
  Write-Host "`nFAILED steps:" -ForegroundColor Red
  $failed | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
  exit 1
}
Write-Host "`nAll sandbox steps passed." -ForegroundColor Green
