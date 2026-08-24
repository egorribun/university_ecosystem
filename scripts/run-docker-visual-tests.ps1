# scripts/run-docker-visual-tests.ps1
# Runs Playwright visual regression tests inside the official Playwright Docker container
# to update or verify Linux-based screenshots.

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

Write-Host "Starting Playwright container (v1.58.2-noble) to run visual E2E tests..." -ForegroundColor Cyan

docker run --rm -it `
  -v "${root}:/work" `
  -w /work/frontend `
  mcr.microsoft.com/playwright:v1.58.2-noble@sha256:6446946a1d9fd62d9ae501312a2d76a43ee688542b21622056a372959b65d63d `
  $playwrightCmd

Write-Host "Visual tests complete." -ForegroundColor Green
