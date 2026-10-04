# scripts/run-docker-visual-tests.ps1
# Runs Playwright visual regression tests inside the official Playwright Docker container
# with Linux browser binaries. The selected suite currently has Windows-only
# baselines; an all-skipped run does not establish Linux visual acceptance.

[CmdletBinding()]
param(
  [switch]$Update
)

$ErrorActionPreference = "Stop"

$root = & git rev-parse --show-toplevel 2>$null
if (-not $root) {
  Write-Error "run-docker-visual-tests.ps1: not in a git repository. Aborting."
  exit 1
}
$root = $root -replace '/', '\'
Set-Location $root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Error "Docker is not running or not found on PATH. Please install Docker Desktop."
  exit 1
}

$playwrightCmd = @("npx", "playwright", "test", "tests/e2e/visual.spec.ts", "--project=chromium")
if ($Update) {
  $playwrightCmd += "--update-snapshots"
}

Write-Warning "The selected snapshot suite currently skips Linux; this command does not complete visual acceptance."
Write-Host "Starting Playwright container (v1.63.0-noble) to run visual E2E tests..." -ForegroundColor Cyan

docker run --rm -it `
  -v "${root}:/work" `
  -w /work/frontend `
  mcr.microsoft.com/playwright:v1.63.0-noble@sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27 `
  $playwrightCmd

$dockerExitCode = $LASTEXITCODE
if ($dockerExitCode -ne 0) {
  exit $dockerExitCode
}

Write-Host "Visual command finished. Review the report for executed and skipped tests."
