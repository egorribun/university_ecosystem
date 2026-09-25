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
# Compose topology overrides and destructive volume removal are deliberately
# unavailable here; use the reviewed cutover launcher/runbook for those flows.
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
$envFile = Join-Path $root ".env.docker"
if (-not (Test-Path -LiteralPath $envFile)) {
  Write-Error "scripts/dc.ps1: ERROR - .env.docker is missing. Run .\start-docker.ps1 once to generate it."
  exit 1
}

# This wrapper intentionally uses the legacy full Compose file. After an S3
# cutover it must not restart that file's MinIO service against the old volume.
# Read-only commands and shutdown remain available for diagnostics/recovery.
$safeCommand = @("ps", "logs", "config", "down", "stop", "images", "top", "ls", "version", "events", "port")
$deletesVolumes = @($args | Where-Object {
  [string]$_ -in @("-v", "--volume", "--volumes") -or
  [string]$_ -like "-v=*" -or [string]$_ -like "--volume=*" -or [string]$_ -like "--volumes=*"
}).Count -gt 0
$deletesImages = @($args | Where-Object {
  [string]$_ -eq "--rmi" -or [string]$_ -like "--rmi=*"
}).Count -gt 0
$composeCommand = ""
$composeCommandIndex = -1
for ($index = 0; $index -lt $args.Count; $index++) {
  $option = [string]$args[$index]
  if (($option -like "-p*" -and $option -ne "-p") -or
      $option -like "-f*" -or $option -eq "--file" -or $option -like "--file=*" -or
      $option -eq "--project-directory" -or $option -like "--project-directory=*" -or
      $option -eq "--env-file" -or $option -like "--env-file=*") {
    Write-Error "scripts/dc.ps1: Compose topology overrides are not supported; use the reviewed storage launcher."
    exit 2
  }
  if ($option -in @("-p", "--project-name")) {
    $index++
    continue
  }
  if ($option -like "--project-name=*") {
    continue
  }
  if ($option.StartsWith("-")) {
    Write-Error "scripts/dc.ps1: Unsupported global Compose option; refusing an unreviewed command shape."
    exit 2
  }
  $composeCommand = $option
  $composeCommandIndex = $index
  break
}
$execPayloadStart = [int]::MaxValue
if ($composeCommand -eq "exec" -and $args.Count -gt $composeCommandIndex + 2 -and
    -not ([string]$args[$composeCommandIndex + 1]).StartsWith("-") -and
    -not ([string]$args[$composeCommandIndex + 2]).StartsWith("-")) {
  # After `exec SERVICE PROGRAM`, remaining flags belong to PROGRAM, not Compose.
  $execPayloadStart = $composeCommandIndex + 3
}
for ($index = 0; $index -lt $args.Count; $index++) {
  if ($index -ge $execPayloadStart) { break }
  $option = [string]$args[$index]
  if ($option -eq "--file" -or $option -like "--file=*" -or
      $option -eq "--project-directory" -or $option -like "--project-directory=*" -or
      $option -eq "--env-file" -or $option -like "--env-file=*" -or
      ($option -like "-f*" -and $composeCommand -notin @("logs", "exec"))) {
    Write-Error "scripts/dc.ps1: Compose topology overrides are not supported; use the reviewed storage launcher."
    exit 2
  }
}
if ($composeCommand -eq "down" -and $deletesVolumes) {
  Write-Error "scripts/dc.ps1: Refusing destructive Compose down --volumes; use a separately reviewed data cleanup procedure."
  exit 2
}
if ($composeCommand -eq "down" -and $deletesImages) {
  Write-Error "scripts/dc.ps1: Refusing Compose down --rmi; preserve the cached legacy S3 image until migration and rollback are verified."
  exit 2
}
$readOnlyCommands = @("ps", "logs", "config", "images", "top", "ls", "version", "events", "port")
$lockOwned = $false
$lockPath = Join-Path $root ".secrets/s3-storage-compose.lock"
$composeExitCode = 1
try {
if ($composeCommand -notin $readOnlyCommands) {
  $secretsDir = Join-Path $root ".secrets"
  if (-not (Test-Path -LiteralPath $secretsDir)) {
    New-Item -ItemType Directory -Path $secretsDir -ErrorAction Stop | Out-Null
  }
  New-Item -ItemType Directory -Path $lockPath -ErrorAction Stop | Out-Null
  $lockOwned = $true
}
if ($composeCommand -notin $safeCommand) {
  $marker = Join-Path $root ".secrets/s3-seaweedfs-cutover-initiated"
  $volumeName = "university_ecosystem_seaweedfs_data"
  if (Test-Path -LiteralPath $marker) {
    Write-Error "scripts/dc.ps1: SeaweedFS cutover marker exists; refusing a possible MinIO rollback. Use start-docker.ps1 -SeaweedFS after runbook verification."
    exit 2
  }

  $composeProject = $env:COMPOSE_PROJECT_NAME
  if ([string]::IsNullOrWhiteSpace($composeProject)) {
    $projectEntry = Get-Content -LiteralPath $envFile |
      Where-Object { $_ -match '^\s*COMPOSE_PROJECT_NAME\s*=' } |
      Select-Object -Last 1
    if ($projectEntry) {
      $composeProject = ($projectEntry -split '=', 2)[1].Trim().Trim('"', "'")
    }
  }
  if ([string]::IsNullOrWhiteSpace($composeProject)) {
    $composeProject = (Split-Path -Leaf $root).ToLowerInvariant()
  }
  for ($index = 0; $index -lt $args.Count; $index++) {
    if ([string]$args[$index] -in @("-p", "--project-name") -and $index + 1 -lt $args.Count) {
      $composeProject = [string]$args[$index + 1]
    } elseif ([string]$args[$index] -like "--project-name=*") {
      $composeProject = ([string]$args[$index] -split '=', 2)[1]
    }
  }
  $storageImages = @(
    docker ps -a `
      --filter "label=com.docker.compose.project=$composeProject" `
      --filter "label=com.docker.compose.service=minio" `
      --format "{{.Image}}" 2>$null
  )
  if ($LASTEXITCODE -ne 0) {
    Write-Error "scripts/dc.ps1: Cannot inspect Compose storage containers; refusing a possible MinIO rollback."
    exit 2
  }
  if (@($storageImages | Where-Object { $_ -match 'seaweedfs' }).Count -gt 0) {
    Write-Error "scripts/dc.ps1: SeaweedFS storage container exists; refusing a possible MinIO rollback."
    exit 2
  }
  $cutoverVolumes = @(
    docker volume ls --filter "name=^$volumeName$" --format "{{.Name}}" 2>$null
  )
  if ($LASTEXITCODE -ne 0) {
    Write-Error "scripts/dc.ps1: Cannot inspect S3 storage volumes; refusing a possible MinIO rollback."
    exit 2
  }
  if ($cutoverVolumes -contains $volumeName) {
    Write-Error "scripts/dc.ps1: SeaweedFS storage volume exists; refusing a possible MinIO rollback."
    exit 2
  }
}

& docker compose -f docker-compose.full.yml --env-file $envFile @args
$composeExitCode = $LASTEXITCODE
} finally {
  if ($lockOwned) {
    Remove-Item -LiteralPath $lockPath -ErrorAction Stop
  }
}
exit $composeExitCode
