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
# unavailable here; use start-docker.ps1 (-ExtraCompose) for other topologies.
# Storage-starting commands share the launcher's legacy MinIO volume guard
# (ADR-042, docs/runbooks/s3-seaweedfs-cutover.md).
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

# Read-only commands and shutdown never start storage and stay available for
# diagnostics/recovery.
$safeCommand = @("ps", "logs", "config", "down", "stop", "images", "top", "ls", "version", "events", "port")
$deletesVolumes = @($args | Where-Object {
  [string]$_ -in @("-v", "--volume", "--volumes") -or
  [string]$_ -like "-v=*" -or [string]$_ -like "--volume=*" -or [string]$_ -like "--volumes=*"
}).Count -gt 0
$composeCommand = ""
$composeCommandIndex = -1
for ($index = 0; $index -lt $args.Count; $index++) {
  $option = [string]$args[$index]
  if (($option -like "-p*" -and $option -ne "-p") -or
      $option -like "-f*" -or $option -eq "--file" -or $option -like "--file=*" -or
      $option -eq "--project-directory" -or $option -like "--project-directory=*" -or
      $option -eq "--env-file" -or $option -like "--env-file=*") {
    Write-Error "scripts/dc.ps1: Compose topology overrides are not supported; use start-docker.ps1 -ExtraCompose."
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
    Write-Error "scripts/dc.ps1: Compose topology overrides are not supported; use start-docker.ps1 -ExtraCompose."
    exit 2
  }
}
if ($composeCommand -eq "down" -and $deletesVolumes) {
  Write-Error "scripts/dc.ps1: Refusing destructive Compose down --volumes; use a separately reviewed data cleanup procedure."
  exit 2
}
if ($composeCommand -notin $safeCommand) {
  # Same rule as start-docker.ps1 Assert-LegacyS3VolumeGuard: never let a
  # wrapper create empty SeaweedFS storage next to an unmigrated legacy MinIO
  # volume, after which nothing could tell that legacy objects were left.
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
    $composeProject = "university_ecosystem"
  }
  for ($index = 0; $index -lt $args.Count; $index++) {
    if ([string]$args[$index] -in @("-p", "--project-name") -and $index + 1 -lt $args.Count) {
      $composeProject = [string]$args[$index + 1]
    } elseif ([string]$args[$index] -like "--project-name=*") {
      $composeProject = ([string]$args[$index] -split '=', 2)[1]
    }
  }
  $legacyVolumes = @("${composeProject}_minio-data", "${composeProject}_minio_data")
  $storageVolume = "${composeProject}_seaweedfs_data"
  # Docker's name filter matches substrings; compare every name exactly.
  $existing = @(docker volume ls --format "{{.Name}}" 2>$null)
  if ($LASTEXITCODE -ne 0) {
    Write-Error "scripts/dc.ps1: Cannot inspect Docker volumes; refusing to start storage without checking for a legacy MinIO volume."
    exit 2
  }
  $legacy = @($legacyVolumes | Where-Object { $existing -ccontains $_ })
  if ($legacy.Count -gt 0) {
    $expectedAttestation = @(
      "schema_version=1",
      "project_name=$composeProject",
      "legacy_source_volumes=$($legacy -join ',')",
      "target_volume=$storageVolume",
      "verified=VERIFIED_S3_CUTOVER"
    )
    $attestationPath = Join-Path $root ".secrets/s3-cutover-attestation.txt"
    $attestationMatches = $false
    if (Test-Path -LiteralPath $attestationPath -PathType Leaf) {
      $actualAttestation = @(Get-Content -LiteralPath $attestationPath)
      $attestationMatches = $actualAttestation.Count -eq $expectedAttestation.Count -and
        [string]::Join("`n", $actualAttestation) -ceq [string]::Join("`n", $expectedAttestation)
    }
    if (($existing -cnotcontains $storageVolume) -or -not $attestationMatches) {
      Write-Error "scripts/dc.ps1: Legacy MinIO volume $($legacy -join ', ') requires existing target '$storageVolume' and exact verified attestation .secrets/s3-cutover-attestation.txt. Follow docs/runbooks/s3-seaweedfs-cutover.md first."
      exit 2
    }
  }
}

& docker compose -f docker-compose.full.yml --env-file $envFile @args
exit $LASTEXITCODE
