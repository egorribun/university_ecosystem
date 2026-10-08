<#
.SYNOPSIS
    Start the University Ecosystem site using Docker Compose.

.DESCRIPTION
    Builds and starts all Docker containers for the full site.
    Generates secure secrets if .env / .env.docker don't exist.
    Reconciles the configured S3 bucket and auxiliary databases on every start.
    Use -PrepareOnly with the owned live overlay to prepare local configuration
    without invoking Docker or starting services.
    Use -Core (or its -Lean alias) for an explicit local resource-constrained
    topology that omits search, Temporal, and observability containers while
    preserving their images and named volumes.

.EXAMPLE
    .\start-docker.ps1            # Start (no rebuild)
    .\start-docker.ps1 -Build     # Build (cached) then start
    .\start-docker.ps1 -Rebuild   # Build (no-cache) then start
    .\start-docker.ps1 -Core      # Start only the application/core dependencies
    .\start-docker.ps1 -PrepareOnly -ExtraCompose docker-compose.live.yml # Prepare owned live config only
    .\start-docker.ps1 -Build -ExtraCompose docker-compose.live.yml  # Owned acceptance stand
    .\start-docker.ps1 -Down      # Stop all containers
    .\start-docker.ps1 -Logs                  # Follow all logs
    .\start-docker.ps1 -Logs -LogService backend  # Follow one service

    The full production-like local stack remains the default.  -Core (also
    available as -Lean) is an explicit local-development opt-in: it stops any
    already-running search, Temporal, and observability services without
    deleting their volumes, then starts only the core application topology.

    Object storage is SeaweedFS (ADR-042). A start with legacy MinIO volumes
    requires the exact project/source/target-bound local migration attestation
    described in docs/runbooks/s3-seaweedfs-cutover.md.
#>

# Advanced-script binding rejects unknown switches, such as the retired
# -SeaweedFS cutover switch, instead of silently ignoring them.
[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$Rebuild,
    [switch]$Down,
    [switch]$Logs,
    [switch]$PrepareOnly,
    [switch]$AllowExistingOwnedVolumes,
    [string]$LiveStandStateRoot = "",
    [ValidateSet("full", "core")]
    [string]$LiveAcceptanceStack = "",
    [string]$LiveAcceptanceServicesJson = "",
    [Alias("Lean")]
    [switch]$Core,
    [string[]]$ExtraCompose = @(),
    [string]$LogService = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $MyInvocation.MyCommand.Path))
$LiveStateMode = -not [string]::IsNullOrWhiteSpace($LiveStandStateRoot)
$StateRoot = $ProjectRoot
$script:LiveStandOwner = $null
$script:LiveAcceptanceRoots = @()
$script:LiveAcceptanceServices = @()
$script:LiveAcceptanceCore = $false
$script:LiveAcceptanceCoreRoots = [string[]]@(
    "caddy",
    "mailpit",
    "notifications-worker",
    "outbox-worker",
    "spicedb"
)
$script:LiveAcceptanceCoreClosure = [string[]]@(
    "backend",
    "caddy",
    "flagd",
    "flagd-healthprobe",
    "frontend",
    "gateway",
    "imgproxy",
    "mailpit",
    "migrations",
    "minio",
    "minio-init",
    "nats",
    "notifications-worker",
    "outbox-worker",
    "postgres",
    "postgres-databases-init",
    "redis",
    "revocation-redis",
    "spicedb",
    "spicedb-migrate",
    "tempo",
    "tempo-healthprobe",
    "ws-hub"
)

function Assert-LiveStandPrivatePath {
    param([Parameter(Mandatory=$true)][string]$Path)
    if (-not $LiveStateMode) { return }

    if ([System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows
    )) {
        try {
            $currentSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
            $systemSid = "S-1-5-18"
            $acl = Get-Acl -LiteralPath $Path -ErrorAction Stop
            $ownerSid = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
        } catch {
            throw "Live stand state permissions cannot be verified."
        }
        if ($ownerSid -cne $currentSid) {
            throw "Live stand state path is not owned by the current Windows user."
        }
        $allowedSids = @($currentSid, $systemSid)
        $seenSids = @{}
        foreach ($rule in $acl.Access) {
            if ($rule.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) {
                continue
            }
            try {
                $identitySid = $rule.IdentityReference.Translate(
                    [System.Security.Principal.SecurityIdentifier]
                ).Value
            } catch {
                throw "Live stand state ACL contains an unverifiable identity."
            }
            if ($identitySid -cnotin $allowedSids -or
                (($rule.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::FullControl) -ne
                    [System.Security.AccessControl.FileSystemRights]::FullControl)) {
                throw "Live stand state ACL grants access beyond the current user and SYSTEM."
            }
            $seenSids[$identitySid] = $true
        }
        if (-not $seenSids.ContainsKey($currentSid) -or
            -not $seenSids.ContainsKey($systemSid)) {
            throw "Live stand state ACL must grant access to the current user and SYSTEM."
        }
        return
    }

    try {
        $mode = [System.IO.File]::GetUnixFileMode($Path)
    } catch {
        throw "Live stand state permissions cannot be verified."
    }
    $groupAndOther = [System.IO.UnixFileMode]::GroupRead -bor
        [System.IO.UnixFileMode]::GroupWrite -bor
        [System.IO.UnixFileMode]::GroupExecute -bor
        [System.IO.UnixFileMode]::OtherRead -bor
        [System.IO.UnixFileMode]::OtherWrite -bor
        [System.IO.UnixFileMode]::OtherExecute
    if (($mode -band $groupAndOther) -ne [System.IO.UnixFileMode]::None) {
        throw "Live stand state paths must have private permissions on POSIX."
    }
}

function Set-LiveStandPrivateFileMode {
    param([Parameter(Mandatory=$true)][string]$Path)
    if (-not $LiveStateMode) { return }
    $absolutePath = [System.IO.Path]::GetFullPath($Path)
    $rootPrefix = $StateRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    $pathComparison = [StringComparison]::Ordinal
    $runningOnWindows = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows
    )
    if ($runningOnWindows) { $pathComparison = [StringComparison]::OrdinalIgnoreCase }
    if (-not $absolutePath.StartsWith($rootPrefix, $pathComparison)) {
        throw "Generated live stand file escapes the owned state root."
    }
    if ($runningOnWindows) {
        $item = Get-Item -LiteralPath $absolutePath -Force
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw "Generated live stand file refuses reparse points."
        }
        $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
        $userSid = $identity.User.Value
        $icacls = Get-Command "icacls.exe" -ErrorAction Stop
        $null = & $icacls.Source $absolutePath "/reset" 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Cannot reset generated live stand file permissions."
        }
        $null = & $icacls.Source $absolutePath "/setowner" "*$userSid" 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Cannot set generated live stand file owner."
        }
        return
    }
    $ownerReadWrite = [System.IO.UnixFileMode]::UserRead -bor
        [System.IO.UnixFileMode]::UserWrite
    [System.IO.File]::SetUnixFileMode($absolutePath, $ownerReadWrite)
}

function Set-LiveStandRuntimeSecretFileMode {
    param([Parameter(Mandatory=$true)][string]$Path)
    if (-not $LiveStateMode) { return }

    $absolutePath = [System.IO.Path]::GetFullPath($Path)
    $relativePath = [System.IO.Path]::GetRelativePath($StateRoot, $absolutePath).Replace('\', '/')
    $allowedPaths = @(
        ".secrets/jwt_rs256.pem",
        ".secrets/jwt_rs256.pub.pem",
        ".secrets/temporal_api_key"
    )
    if ($relativePath -cnotin $allowedPaths) {
        throw "Runtime secret permissions can be relaxed only for explicitly mounted live files."
    }
    if (-not (Test-Path -LiteralPath $absolutePath -PathType Leaf)) {
        throw "Required live runtime secret file is missing."
    }
    $item = Get-Item -LiteralPath $absolutePath -Force
    if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        throw "Live runtime secret file refuses reparse points."
    }
    if ([System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows
    )) {
        Set-LiveStandPrivateFileMode -Path $absolutePath
        return
    }

    $runtimeReadableMode = [System.IO.UnixFileMode]::UserRead -bor
        [System.IO.UnixFileMode]::UserWrite -bor
        [System.IO.UnixFileMode]::GroupRead -bor
        [System.IO.UnixFileMode]::OtherRead
    [System.IO.File]::SetUnixFileMode($absolutePath, $runtimeReadableMode)
}

function ConvertTo-CanonicalLiveOwnerJson {
    param([Parameter(Mandatory=$true)][AllowNull()]$Value)
    if ($null -eq $Value) { return "null" }
    if ($Value -is [System.Collections.IDictionary]) {
        $members = foreach ($key in ($Value.Keys | Sort-Object -CaseSensitive)) {
            $keyJson = ConvertTo-Json -InputObject ([string]$key) -Compress
            $valueJson = ConvertTo-CanonicalLiveOwnerJson -Value $Value[$key]
            "${keyJson}:$valueJson"
        }
        return "{$($members -join ',')}"
    }
    if ($Value -is [array]) {
        $members = foreach ($item in $Value) {
            ConvertTo-CanonicalLiveOwnerJson -Value $item
        }
        return "[$($members -join ',')]"
    }
    if ($Value -is [string]) {
        return ConvertTo-Json -InputObject $Value -Compress
    }
    if ($Value -is [bool]) {
        return $Value.ToString().ToLowerInvariant()
    }
    return ConvertTo-Json -InputObject $Value -Compress
}

function Test-CanonicalLiveServiceList {
    param(
        [Parameter(Mandatory=$true)][AllowEmptyCollection()][object]$Value,
        [switch]$AllowEmpty
    )
    if ($Value -isnot [array]) { return $false }
    $items = @($Value)
    if (-not $AllowEmpty -and $items.Count -eq 0) { return $false }
    foreach ($item in $items) {
        if ($item -isnot [string] -or
            $item -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$') {
            return $false
        }
    }
    $unique = @($items | Sort-Object -Unique -CaseSensitive)
    $sorted = @($items | Sort-Object -CaseSensitive)
    if ($unique.Count -ne $items.Count -or $sorted.Count -ne $items.Count) {
        return $false
    }
    for ($index = 0; $index -lt $items.Count; $index++) {
        if ([string]$items[$index] -cne [string]$sorted[$index]) { return $false }
    }
    return $true
}

function Resolve-OwnedLiveStandStateRoot {
    param([Parameter(Mandatory=$true)][string]$Path)
    $candidate = [System.IO.Path]::GetFullPath($Path)
    $temporaryParent = [System.IO.Path]::GetFullPath(
        (Join-Path ([System.IO.Path]::GetTempPath()) "ue-live-acceptance")
    )
    $parent = [System.IO.Path]::GetDirectoryName($candidate)
    $runName = [System.IO.Path]::GetFileName($candidate)
    if ($parent.TrimEnd('\', '/') -ine $temporaryParent.TrimEnd('\', '/') -or
        $runName -notmatch '^run-[A-Za-z0-9-]{1,80}$' -or
        $candidate.TrimEnd('\', '/') -ieq $ProjectRoot.TrimEnd('\', '/') -or
        $ProjectRoot.StartsWith($candidate.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
        $candidate.StartsWith($ProjectRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Live stand state root must be a direct run child of the owned temporary root."
    }
    foreach ($pathToCheck in @($temporaryParent, $candidate)) {
        $current = $pathToCheck
        while ($current) {
            if (Test-Path -LiteralPath $current) {
                $item = Get-Item -LiteralPath $current -Force
                if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                    throw "Live stand state root refuses reparse points."
                }
            }
            if (-not [System.IO.Path]::GetDirectoryName($current) -or
                [System.IO.Path]::GetDirectoryName($current) -ceq $current) { break }
            $current = [System.IO.Path]::GetDirectoryName($current)
        }
    }
    if (-not (Test-Path -LiteralPath $candidate -PathType Container)) {
        throw "Live stand state root does not exist."
    }
    $ownerPath = Join-Path $candidate ".secrets/live-stand.json"
    $keyPath = Join-Path $candidate ".secrets/live-stand-owner.key"
    foreach ($ownedFile in @($ownerPath, $keyPath, (Join-Path $candidate "docker-compose.live-state.yml"))) {
        if (-not (Test-Path -LiteralPath $ownedFile -PathType Leaf)) {
            throw "Live stand state root is missing an owned marker, key, or Compose override."
        }
        $item = Get-Item -LiteralPath $ownedFile -Force
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw "Live stand state root contains an unsafe owned file path."
        }
    }
    $secretsDirectory = Get-Item -LiteralPath (Join-Path $candidate ".secrets") -Force
    if (-not $secretsDirectory.PSIsContainer -or
        ($secretsDirectory.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw "Live stand state root has an unsafe secrets directory."
    }
    foreach ($privatePath in @(
        $candidate,
        $secretsDirectory.FullName,
        $ownerPath,
        $keyPath,
        (Join-Path $candidate "docker-compose.live-state.yml")
    )) {
        Assert-LiveStandPrivatePath -Path $privatePath
    }
    try {
        $owner = [System.IO.File]::ReadAllText($ownerPath) | ConvertFrom-Json -AsHashtable -ErrorAction Stop
        $key = [System.IO.File]::ReadAllBytes($keyPath)
    } catch {
        throw "Live stand ownership metadata cannot be validated."
    }
    if ($owner.version -notin @(7, 9) -or
        [string]$owner.repository -ine $ProjectRoot -or
        [string]$owner.worktree -ine $candidate -or
        [string]$owner.project_name -cnotmatch '^ue-live-[0-9a-f]{16}$' -or
        [string]$owner.source_sha -cnotmatch '^[0-9a-f]{40}$' -or
        [string]$env:LIVE_STAND_SOURCE_SHA -cne [string]$owner.source_sha -or
        [string]$env:COMPOSE_PROJECT_NAME -cne [string]$owner.project_name -or
        $key.Length -ne 32 -or
        [string]$owner.signature -cnotmatch '^[0-9a-f]{64}$') {
        throw "Live stand owner does not match this source checkout and run root."
    }
    if ($owner.version -eq 7) {
        if ($owner.ContainsKey("stack") -or $owner.ContainsKey("service_roots") -or
            $owner.ContainsKey("selected_services")) {
            throw "Legacy live stand owner contains unsupported stack metadata."
        }
    } else {
        if (-not $owner.ContainsKey("stack") -or
            [string]$owner.stack -cnotin @("full", "core") -or
            -not $owner.ContainsKey("service_roots") -or
            -not $owner.ContainsKey("selected_services") -or
            -not (Test-CanonicalLiveServiceList -Value $owner.service_roots -AllowEmpty) -or
            -not (Test-CanonicalLiveServiceList -Value $owner.selected_services -AllowEmpty)) {
            throw "Live stand owner has an invalid signed service selection."
        }
        $resourceFingerprint = $owner.compose_resource_fingerprint
        $completeSelection = $null -ne $resourceFingerprint
        if ($completeSelection -and
            ($resourceFingerprint -isnot [string] -or
                $resourceFingerprint -cnotmatch '^[0-9a-f]{64}$')) {
            throw "Live stand owner has an invalid resource fingerprint."
        }
        $ownerRootsText = [string]::Join("`n", [string[]]@($owner.service_roots))
        $ownerServicesText = [string]::Join("`n", [string[]]@($owner.selected_services))
        if ([string]$owner.stack -ceq "core") {
            if ($ownerRootsText -cne [string]::Join("`n", $script:LiveAcceptanceCoreRoots) -or
                ($completeSelection -and
                    $ownerServicesText -cne [string]::Join("`n", $script:LiveAcceptanceCoreClosure)) -or
                (-not $completeSelection -and @($owner.selected_services).Count -ne 0)) {
                throw "Live Core owner has an invalid signed service closure."
            }
        } elseif ($completeSelection) {
            if (@($owner.selected_services).Count -eq 0 -or
                $ownerRootsText -cne $ownerServicesText) {
                throw "Full live owner roots and services do not match."
            }
        } elseif (@($owner.service_roots).Count -ne 0 -or
            @($owner.selected_services).Count -ne 0) {
            throw "Incomplete full live owner contains a service selection."
        }
    }
    $payload = [ordered]@{}
    foreach ($name in ($owner.Keys | Where-Object { $_ -cne "signature" } | Sort-Object -CaseSensitive)) {
        $payload[$name] = $owner[$name]
    }
    $canonical = ConvertTo-CanonicalLiveOwnerJson -Value $payload
    $hmac = [System.Security.Cryptography.HMACSHA256]::new($key)
    try {
        $actualSignature = [Convert]::ToHexString(
            $hmac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($canonical))
        ).ToLowerInvariant()
    } finally {
        $hmac.Dispose()
        [Array]::Clear($key, 0, $key.Length)
    }
    if (-not [System.Security.Cryptography.CryptographicOperations]::FixedTimeEquals(
        [Convert]::FromHexString([string]$owner.signature),
        [Convert]::FromHexString($actualSignature)
    )) {
        throw "Live stand owner signature is invalid."
    }
    $script:LiveStandOwner = $owner
    return $candidate
}

function Resolve-StatePath {
    param([Parameter(Mandatory=$true)][string]$Path)
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $StateRoot $Path))
}

if ($LiveStateMode) {
    $StateRoot = Resolve-OwnedLiveStandStateRoot -Path $LiveStandStateRoot
}
Set-Location $StateRoot

$ComposeFile = "docker-compose.full.yml"
$S3MigrationRunbook = "docs/runbooks/s3-seaweedfs-cutover.md"
$S3MigrationAttestation = if ($LiveStateMode) {
    Join-Path $StateRoot ".secrets/s3-cutover-attestation.txt"
} else { ".secrets/s3-cutover-attestation.txt" }
$ComposeArgs = if ($LiveStateMode) {
    @("--project-directory", $ProjectRoot, "-f", (Join-Path $ProjectRoot $ComposeFile))
} else { @("-f", $ComposeFile) }
foreach ($extra in $ExtraCompose) {
    # Additional overlays stay inside the checkout, follow the repository's
    # Compose naming, and apply after the base file.
    if ($extra -notmatch '^docker-compose\.[a-z0-9-]+\.yml$') {
        throw "Extra Compose overlay refused: expected a docker-compose.<name>.yml file in the project root: $extra"
    }
    if ($extra -eq $ComposeFile) {
        throw "Extra Compose overlay refused: $extra is the base Compose file"
    }
    $extraPath = Join-Path $ProjectRoot $extra
    if (-not (Test-Path -LiteralPath $extraPath -PathType Leaf)) {
        throw "Extra Compose overlay refused: file not found: $extra"
    }
    if ($ComposeArgs -contains $extraPath -or $ComposeArgs -contains $extra) {
        throw "Extra Compose overlay refused: $extra is listed twice"
    }
    $ComposeArgs += @("-f", $(if ($LiveStateMode) { $extraPath } else { $extra }))
}
if ($LiveStateMode) {
    $ComposeArgs += @("-f", (Join-Path $StateRoot "docker-compose.live-state.yml"))
}
$ComposeCommand = "docker compose $($ComposeArgs -join ' ') --env-file .env.docker"

$liveSelectionArgumentsPresent = (
    -not [string]::IsNullOrEmpty($LiveAcceptanceStack) -or
    -not [string]::IsNullOrEmpty($LiveAcceptanceServicesJson)
)
if ($liveSelectionArgumentsPresent) {
    if (-not ($Build -or $Rebuild) -or $Down -or $Logs -or $PrepareOnly -or $Core -or
        @($ExtraCompose).Count -ne 1 -or
        $ExtraCompose[0] -cne "docker-compose.live.yml") {
        throw "Live acceptance selection requires a build of the owned live overlay."
    }
}
# Keep the full compose model as the single source of truth.  Core mode scopes
# `up`/`build` to this audited allowlist rather than maintaining a second compose
# file that could silently drift in images, networks, or security settings.
$CoreBootstrapServices = [string[]]@(
    "postgres",
    "redis",
    "revocation-redis",
    "minio",
    "nats",
    "flagd"
)
$CoreInitServices = [string[]]@(
    "postgres-databases-init",
    "minio-init",
    "migrations",
    "spicedb-migrate"
)
$CoreRuntimeServices = [string[]]@(
    "flagd-healthprobe",
    "spicedb",
    "backend",
    "frontend",
    "notifications-worker",
    "outbox-worker",
    "gateway",
    "ws-hub",
    "imgproxy",
    "caddy"
)
$CoreComposeServices = [string[]]@(
    $CoreBootstrapServices + $CoreInitServices + $CoreRuntimeServices
)
# These names are intentionally separate from the health-map aliases below:
# Compose service names are used to stop already-running optional containers,
# while health-map keys are human-readable and may use a compact alias.
$CoreOptionalComposeServices = [string[]]@(
    "redis-exporter",
    "elasticsearch",
    "file-processor",
    "temporal-admin-tools",
    "temporal",
    "temporal-namespace-init",
    "grafana",
    "prometheus",
    "tempo",
    "tempo-healthprobe",
    "loki",
    "loki-healthprobe",
    "alloy",
    "pyroscope"
)
$CoreExcludedHealthServices = [string[]]@(
    "redisexporter",
    "elasticsearch",
    "fileprocessor",
    "temporal",
    "grafana",
    "prometheus",
    "tempo",
    "tempo-healthprobe",
    "loki",
    "loki-healthprobe",
    "alloy",
    "pyroscope"
)
$EnvFile = ".env.docker"
$WorkerEnvFile = ".env.docker.workers"
$EnvCompose = ".env"
if ($LiveStateMode) {
    $EnvFile = Join-Path $StateRoot ".env.docker"
    $WorkerEnvFile = Join-Path $StateRoot ".env.docker.workers"
    $EnvCompose = Join-Path $StateRoot ".env"
}
$OpenSslFallbackImage = "alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc"

# -- Helpers ------------------------------------------------------------------

function Write-Status  { param([string]$Msg) Write-Host "[*] $Msg" -ForegroundColor Cyan }
function Write-Ok      { param([string]$Msg) Write-Host "[+] $Msg" -ForegroundColor Green }
function Write-Err     { param([string]$Msg) Write-Host "[-] $Msg" -ForegroundColor Red }
function Write-Warn    { param([string]$Msg) Write-Host "[!] $Msg" -ForegroundColor Yellow }

function Assert-CoreServiceAllowlist {
    # Core mode is a resource-control boundary, so fail closed if a future
    # edit accidentally adds an optional service or duplicates an entry.  This
    # keeps the mode auditable while the full stack remains unchanged.
    $forbidden = @($CoreOptionalComposeServices)
    $overlap = @($CoreComposeServices | Where-Object { $_ -in $forbidden })
    if ($overlap.Count -gt 0) {
        throw "Core service allowlist includes forbidden optional services: $($overlap -join ', ')"
    }

    $unique = @($CoreComposeServices | Sort-Object -Unique)
    if ($unique.Count -ne $CoreComposeServices.Count) {
        throw "Core service allowlist contains duplicate service names; refusing to start."
    }
}

function Assert-PrepareOnlyLiveInputs {
    # This mode is the first phase of the owner-checked live-stand startup.
    # Restrict it to the exact overlay and signed project/port/key environment
    # supplied by live_stand.py; never turn it into a generic config writer.
    if ($Build -or $Rebuild -or $Down -or $Logs -or $Core -or $AllowExistingOwnedVolumes -or
        -not [string]::IsNullOrEmpty($LiveAcceptanceStack) -or
        -not [string]::IsNullOrEmpty($LiveAcceptanceServicesJson) -or
        -not [string]::IsNullOrWhiteSpace($LogService)) {
        throw "PrepareOnly cannot be combined with build, lifecycle, log, or core-mode switches."
    }
    if (@($ExtraCompose).Count -ne 1 -or
        $ExtraCompose[0] -cne "docker-compose.live.yml") {
        throw "PrepareOnly requires exactly -ExtraCompose docker-compose.live.yml."
    }
    if ($env:COMPOSE_PROJECT_NAME -cnotmatch '^ue-live-[0-9a-f]{16}$') {
        throw "PrepareOnly requires a valid owned live-stand project name."
    }

    $secretsDirectory = Join-Path $StateRoot ".secrets"
    if (Test-Path -LiteralPath $secretsDirectory) {
        $secretsItem = Get-Item -LiteralPath $secretsDirectory -Force
        if (-not $secretsItem.PSIsContainer -or
            ($secretsItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            throw "PrepareOnly requires a private secrets directory owned by this worktree."
        }
    }
    foreach ($path in @($EnvFile, $EnvCompose, $WorkerEnvFile)) {
        $absolutePath = Resolve-StatePath -Path $path
        if (Test-Path -LiteralPath $absolutePath) {
            $environmentItem = Get-Item -LiteralPath $absolutePath -Force
            if ($environmentItem.PSIsContainer -or
                ($environmentItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
                throw "PrepareOnly refuses an unsafe environment file path."
            }
        }
    }

    $portNames = @(
        "BACKEND", "FRONTEND", "POSTGRES", "GATEWAY", "WS_HUB",
        "TEMPORAL_GRPC", "TEMPORAL_WEB", "IMGPROXY", "GRAFANA",
        "PROMETHEUS", "ALLOY", "PYROSCOPE", "CADDY_HTTP", "CADDY_HTTPS",
        "MAILPIT"
    )
    $publishedPorts = @{}
    $seenPorts = @{}
    foreach ($portName in $portNames) {
        $variableName = if ($portName -eq "MAILPIT") {
            "LIVE_MAILPIT_PORT"
        } else {
            "LIVE_HOST_PORT_$portName"
        }
        $rawPort = [Environment]::GetEnvironmentVariable($variableName)
        $port = 0
        if ([string]::IsNullOrWhiteSpace($rawPort) -or
            $rawPort -notmatch '^\d+$' -or
            -not [int]::TryParse($rawPort, [ref]$port) -or
            $port -lt 1024 -or $port -gt 65535 -or
            $seenPorts.ContainsKey($port)) {
            throw "PrepareOnly requires a complete, unique live-stand port map."
        }
        $publishedPorts[$portName] = $port
        $seenPorts[$port] = $true
    }

    $expectedBaseUrl = "http://localhost:$($publishedPorts['CADDY_HTTP'])"
    if ($env:LIVE_BASE_URL -cne $expectedBaseUrl) {
        throw "PrepareOnly requires the live-stand loopback base URL."
    }

    $publicKey = $env:LIVE_VAPID_PUBLIC_KEY
    $privateKey = $env:LIVE_VAPID_PRIVATE_KEY
    if ($publicKey -notmatch '^[A-Za-z0-9_-]{87}$' -or
        $privateKey -notmatch '^[A-Za-z0-9_-]{43}$') {
        throw "PrepareOnly requires a valid live-stand VAPID key pair."
    }

    $vapidPath = Join-Path $StateRoot ".secrets/live-vapid.json"
    $vapidItem = Get-Item -LiteralPath $vapidPath -Force -ErrorAction SilentlyContinue
    if ($null -eq $vapidItem -or $vapidItem.PSIsContainer -or
        ($vapidItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw "PrepareOnly requires the current worktree's VAPID key file."
    }
    try {
        $vapidData = Get-Content -LiteralPath $vapidPath -Raw | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "PrepareOnly could not validate the current worktree's VAPID key file."
    }
    if ([string]$vapidData.public -cne $publicKey -or
        [string]$vapidData.private -cne $privateKey) {
        throw "PrepareOnly VAPID inputs do not match the current worktree's key file."
    }

    $standardPublicKey = $publicKey.Replace('-', '+').Replace('_', '/') + "="
    $standardPrivateKey = $privateKey.Replace('-', '+').Replace('_', '/') + "="
    try {
        $publicBytes = [Convert]::FromBase64String($standardPublicKey)
        $privateBytes = [Convert]::FromBase64String($standardPrivateKey)
    } catch {
        throw "PrepareOnly requires a valid live-stand VAPID key pair."
    }
    if ($publicBytes.Length -ne 65 -or $publicBytes[0] -ne 4 -or
        $privateBytes.Length -ne 32) {
        throw "PrepareOnly requires a valid live-stand VAPID key pair."
    }
}

if ($AllowExistingOwnedVolumes) {
    if (@($ExtraCompose).Count -ne 1 -or
        $ExtraCompose[0] -cne "docker-compose.live.yml" -or
        $env:COMPOSE_PROJECT_NAME -cnotmatch '^ue-live-[0-9a-f]{16}$') {
        throw "AllowExistingOwnedVolumes is restricted to a verified live-stand project."
    }
}

Assert-CoreServiceAllowlist
if ($PrepareOnly) { Assert-PrepareOnlyLiveInputs }

function New-Secret {
    param([int]$Length = 32)
    $chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    $builder = [System.Text.StringBuilder]::new($Length)
    for ($i = 0; $i -lt $Length; $i++) {
        $index = [System.Security.Cryptography.RandomNumberGenerator]::GetInt32($chars.Length)
        $null = $builder.Append($chars[$index])
    }
    return $builder.ToString()
}

function New-HexSecret {
    param([int]$Length = 32)
    $bytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes($Length)
    return [System.Convert]::ToHexString($bytes).ToLowerInvariant()
}

function New-FernetKey {
    # Fernet requires exactly 32 random bytes encoded with padded URL-safe
    # Base64. Keep this native so a fresh launcher does not depend on Python.
    $bytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    return [System.Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_')
}

function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    $absolutePath = Resolve-StatePath -Path $Path
    [System.IO.File]::WriteAllText(
        $absolutePath,
        $Content,
        [System.Text.UTF8Encoding]::new($false)
    )
    Set-LiveStandPrivateFileMode -Path $absolutePath
}

function Get-EnvEntry {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Key
    )

    $absolutePath = Resolve-StatePath -Path $Path
    if (-not (Test-Path -LiteralPath $absolutePath)) { return $null }

    $prefix = "$Key="
    $line = Get-Content -LiteralPath $absolutePath -ErrorAction SilentlyContinue |
        Where-Object { $_.StartsWith($prefix, [StringComparison]::Ordinal) } |
        Select-Object -First 1
    if ($null -eq $line) { return $null }
    return $line.Substring($prefix.Length).Trim()
}

function Set-EnvEntry {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Key,
        [Parameter(Mandatory=$true)][string]$Value
    )

    $absolutePath = Resolve-StatePath -Path $Path
    $prefix = "$Key="
    $found = $false
    $updated = @(
        Get-Content -LiteralPath $absolutePath -ErrorAction SilentlyContinue |
            ForEach-Object {
                if ($_.StartsWith($prefix, [StringComparison]::Ordinal)) {
                    $found = $true
                    "$Key=$Value"
                } else {
                    $_
                }
            }
    )
    if (-not $found) { $updated += "$Key=$Value" }
    Write-Utf8NoBom -Path $Path -Content "$(($updated -join "`n").TrimEnd())`n"
}

function Ensure-ImgproxyEnvironment {
    # .env.docker is canonical because both the backend signer and imgproxy read
    # it. Keep .env synchronized for Compose interpolation and migrate the old
    # frontend URL, which could never serve signed image paths.
    $specs = @(
        @{ Key = "IMGPROXY_KEY"; Bytes = 32 },
        @{ Key = "IMGPROXY_SALT"; Bytes = 32 }
    )

    foreach ($spec in $specs) {
        $value = Get-EnvEntry -Path $EnvFile -Key $spec.Key
        # Accept any even-length hex value of at least 32 bytes. This matches
        # the backend validator and preserves deliberately longer user keys.
        $pattern = "^(?:[0-9a-fA-F]{2}){$($spec.Bytes),}$"
        if (-not $value -or $value -notmatch $pattern) {
            $value = New-HexSecret -Length $spec.Bytes
            Set-EnvEntry -Path $EnvFile -Key $spec.Key -Value $value
            Write-Ok "Generated $($spec.Key) for signed image URLs"
        }

        if ((Get-EnvEntry -Path $EnvCompose -Key $spec.Key) -ne $value) {
            Set-EnvEntry -Path $EnvCompose -Key $spec.Key -Value $value
        }
    }

    $baseUrl = Get-EnvEntry -Path $EnvFile -Key "IMGPROXY_BASE_URL"
    if (-not $baseUrl -or $baseUrl -eq "http://localhost:8081") {
        $baseUrl = "http://localhost/imgproxy"
        Set-EnvEntry -Path $EnvFile -Key "IMGPROXY_BASE_URL" -Value $baseUrl
        Write-Ok "Configured IMGPROXY_BASE_URL through Caddy"
    }
    if ((Get-EnvEntry -Path $EnvCompose -Key "IMGPROXY_BASE_URL") -ne $baseUrl) {
        Set-EnvEntry -Path $EnvCompose -Key "IMGPROXY_BASE_URL" -Value $baseUrl
    }
}

function Ensure-MetricsEnvironment {
    # Prometheus authenticates to the backend /metrics endpoint. Keep one
    # launcher-managed credential in both environment files so the backend and
    # Prometheus receive the same value without committing it to the repository.
    # prometheus.yml intentionally uses a fixed non-secret identity. Do not
    # preserve an arbitrary legacy username or the two sides will disagree.
    $username = "metrics_scraper"

    $password = Get-EnvEntry -Path $EnvFile -Key "METRICS_BASIC_AUTH_PASSWORD"
    if (-not $password -or $password.Length -lt 32 -or $password -match "CHANGE_ME") {
        $password = New-Secret -Length 48
        Write-Ok "Generated backend metrics scrape credentials"
    }

    foreach ($path in @($EnvFile, $EnvCompose)) {
        Set-EnvEntry -Path $path -Key "ENABLE_METRICS_ENDPOINT" -Value "true"
        Set-EnvEntry -Path $path -Key "METRICS_BASIC_AUTH_USERNAME" -Value $username
        Set-EnvEntry -Path $path -Key "METRICS_BASIC_AUTH_PASSWORD" -Value $password
    }
}

function Ensure-ApplicationSecrets {
    # Remove development fallbacks that couple unrelated security domains to
    # SECRET_KEY. .env.docker remains canonical and .env is synchronized for
    # values interpolated directly into Compose service environments.
    $specs = @(
        # Security-state Redis has a distinct credential from the eviction-enabled
        # cache. Do not merge this with REDIS_PASSWORD: cache-only workers must
        # be unable to erase revoked-JTI tombstones.
        @{ Key = "REVOCATION_REDIS_PASSWORD"; Length = 32; Fernet = $false },
        @{ Key = "TOKEN_HMAC_SECRET"; Length = 48; Fernet = $false },
        @{ Key = "CSRF_HMAC_SECRET"; Length = 48; Fernet = $false },
        @{ Key = "INTERNAL_HMAC_SECRET"; Length = 48; Fernet = $false },
        @{ Key = "IDEMPOTENCY_HMAC_SECRET"; Length = 48; Fernet = $false },
        @{ Key = "SPOTIFY_TOKEN_SECRET"; Length = 44; Fernet = $true },
        @{ Key = "SPOTIFY_OAUTH_STATE_SECRET"; Length = 48; Fernet = $false }
    )

    foreach ($spec in $specs) {
        $value = Get-EnvEntry -Path $EnvFile -Key $spec.Key
        $invalid = -not $value -or $value -match "CHANGE_ME"
        if ($spec.Fernet) {
            $invalid = $invalid -or $value -notmatch '^[A-Za-z0-9_-]{43}=$'
        } else {
            $invalid = $invalid -or $value.Length -lt 32
        }

        if ($invalid) {
            $value = if ($spec.Fernet) { New-FernetKey } else { New-Secret -Length $spec.Length }
            Write-Ok "Generated independent $($spec.Key)"
        }

        foreach ($path in @($EnvFile, $EnvCompose)) {
            if ((Get-EnvEntry -Path $path -Key $spec.Key) -ne $value) {
                Set-EnvEntry -Path $path -Key $spec.Key -Value $value
            }
        }
    }
}

function Assert-IndependentRedisCredentials {
    # .env.docker is the canonical source. Do this before syncing Compose
    # interpolation so a pre-existing manual configuration cannot silently
    # collapse cache and security-state Redis into one credential domain.
    $cachePassword = Get-EnvEntry -Path $EnvFile -Key "REDIS_PASSWORD"
    $revocationPassword = Get-EnvEntry -Path $EnvFile -Key "REVOCATION_REDIS_PASSWORD"
    if (-not [string]::IsNullOrWhiteSpace($cachePassword) -and
        -not [string]::IsNullOrWhiteSpace($revocationPassword) -and
        $cachePassword -ceq $revocationPassword) {
        throw "REDIS_PASSWORD and REVOCATION_REDIS_PASSWORD must differ; refusing to start with a shared cache and revocation credential."
    }
}

function Write-WorkerEnvironmentFile {
    # The full stack's canonical application environment also contains the
    # dedicated revocation-store password and URL. Background workers never
    # authenticate sessions, so materialize a separate env_file instead of
    # handing them a broad credential-bearing environment and relying only on
    # network isolation. The redacted file remains ignored by Git.
    $sourcePath = Resolve-StatePath -Path $EnvFile
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        throw "Cannot create ${WorkerEnvFile}: ${EnvFile} is missing."
    }

    $redactedPattern = '^\s*REVOCATION_REDIS_(?:URL|PASSWORD)='
    $workerLines = @(
        Get-Content -LiteralPath $sourcePath | Where-Object {
            $_ -notmatch $redactedPattern
        }
    )
    if ($workerLines.Count -eq 0) {
        throw "Cannot create ${WorkerEnvFile}: redacted environment is empty."
    }

    Write-Utf8NoBom -Path $WorkerEnvFile -Content "$(($workerLines -join "`n").TrimEnd())`n"
}

function Ensure-JwtEnvironment {
    # The launcher-managed keypair is the single signing source for both the
    # full and base Compose modes, so keep their environment files aligned.
    foreach ($path in @($EnvFile, $EnvCompose)) {
        Set-EnvEntry -Path $path -Key "ALGORITHM" -Value "RS256"
        Set-EnvEntry -Path $path -Key "JWT_AUDIENCE" -Value "university-ecosystem-api"
        Set-EnvEntry -Path $path -Key "JWT_ISSUER" -Value "university-ecosystem"
        Set-EnvEntry -Path $path -Key "JWT_PRIVATE_KEY_PATH" -Value ".secrets/jwt_rs256.pem"
    }
}

function Ensure-DockerConfigRevision {
    # Compose does not notice changes inside bind-mounted files. Fold every
    # runtime configuration file into a deterministic label so `compose up`
    # recreates only the affected configuration-driven services after a pull.
    $relativePaths = @(
        "config/nats.conf.template",
        "services/temporal/config.yaml",
        "services/temporal/entrypoint.sh",
        "infrastructure/observability/prometheus.yml",
        "infrastructure/observability/alerts/gateway.yaml",
        "infrastructure/observability/tempo.yaml",
        "infrastructure/observability/loki.yaml",
        "infrastructure/observability/alloy/config.alloy",
        "infrastructure/observability/grafana/provisioning/datasources/datasources.yaml",
        "k8s/flagd/flags.json",
        "infrastructure/Caddyfile"
    )
    $manifest = foreach ($relativePath in $relativePaths) {
        $absolutePath = Join-Path $ProjectRoot $relativePath
        if (-not (Test-Path -LiteralPath $absolutePath)) {
            throw "Runtime configuration file is missing: $relativePath"
        }
        "$relativePath=$((Get-FileHash -LiteralPath $absolutePath -Algorithm SHA256).Hash)"
    }

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes(($manifest -join "`n"))
        $revision = [System.Convert]::ToHexString($sha256.ComputeHash($bytes)).ToLowerInvariant()
    } finally {
        $sha256.Dispose()
    }

    foreach ($path in @($EnvFile, $EnvCompose)) {
        Set-EnvEntry -Path $path -Key "DOCKER_CONFIG_REVISION" -Value $revision
    }
}

# Validate an existing launcher-managed private key before treating it as an
# idempotent result. A truncated or public-only PEM would otherwise make every
# backend restart fail until the user manually deleted the file.
function Test-JwtRs256PrivateKey {
    param([Parameter(Mandatory=$true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $pem = [System.IO.File]::ReadAllText($Path)
        $rsa = [System.Security.Cryptography.RSA]::Create()
        try {
            $rsa.ImportFromPem($pem)
            $privateParameters = $rsa.ExportParameters($true)
            return $rsa.KeySize -ge 2048 -and $null -ne $privateParameters.D -and $privateParameters.D.Length -gt 0
        } finally {
            $rsa.Dispose()
        }
    } catch {
        return $false
    }
}

# Wave 137 SW1: Generate RSA-2048 keypair for backend JWT RS256 signing.
# Idempotent only after validating the existing private key.
# Uses .NET 8 native PEM export (PowerShell 7+ ships .NET 8 with
# RSA.ExportPkcs8PrivateKeyPem). Falls back to OpenSSL if available.
# Closes W135 sec.Honesty #9 SSR auth-at-edge layer (jose.createRemoteJWKSet
# requires RS256; pre-W137 dev backend signed HS256).
function New-JwtRs256Key {
    param(
        [string]$OutputPath = ".secrets/jwt_rs256.pem",
        [switch]$NoDockerFallback
    )

    $absoluteOutputPath = Resolve-StatePath -Path $OutputPath
    if (Test-JwtRs256PrivateKey -Path $absoluteOutputPath) {
        Write-Ok "RSA-2048 keypair already exists at $OutputPath (idempotent skip)"
        return
    }
    if (Test-Path -LiteralPath $absoluteOutputPath) {
        Write-Warn "RSA private key at $OutputPath is invalid; regenerating"
    }

    Write-Status "Generating RSA-2048 keypair for JWT RS256 signing..."

    $secretsDir = Split-Path $absoluteOutputPath -Parent
    if (-not (Test-Path $secretsDir)) {
        New-Item -ItemType Directory -Path $secretsDir -Force | Out-Null
    }

    $pem = $null
    try {
        # Path A: .NET 8 native PEM export (preferred, no external deps)
        $rsa = [System.Security.Cryptography.RSA]::Create(2048)
        try {
            $pem = $rsa.ExportPkcs8PrivateKeyPem()
        } finally {
            $rsa.Dispose()
        }
    } catch {
        # Path B: host openssl fallback (requires openssl in PATH)
        if (Get-Command openssl -ErrorAction SilentlyContinue) {
            $tempKey = [System.IO.Path]::GetTempFileName()
            try {
                $null = openssl genrsa -out $tempKey 2048 2>&1
                if ($LASTEXITCODE -eq 0) {
                    $pem = Get-Content $tempKey -Raw
                }
            } finally {
                Remove-Item $tempKey -ErrorAction SilentlyContinue
            }
        }

        # Path C: docker fallback (runs openssl in lightweight container if host openssl unavailable)
        if (-not $pem -and -not $NoDockerFallback -and
            (Get-Command docker -ErrorAction SilentlyContinue)) {
            Write-Status "Falling back to Docker openssl for keypair generation..."
            $pem = docker run --rm $OpenSslFallbackImage sh -c "apk add --no-cache openssl >/dev/null 2>&1; openssl genrsa 2048 2>/dev/null" 2>&1 | Out-String
            if ($LASTEXITCODE -ne 0 -or $pem -notmatch "BEGIN (RSA )?PRIVATE KEY") {
                $pem = $null
            }
        }
    }

    if (-not $pem) {
        throw "Failed to generate RSA private key - neither .NET, host openssl, nor docker openssl succeeded."
    }

    [System.IO.File]::WriteAllText(
        $absoluteOutputPath,
        $pem.Trim(),
        [System.Text.UTF8Encoding]::new($false)
    )
    Set-LiveStandPrivateFileMode -Path $absoluteOutputPath

    Write-Ok "Generated RSA-2048 keypair at $OutputPath"
}

# Derive the RSA public key used directly by file-processor. Temporal validates
# through the backend JWKS endpoint, which serves the same private key's public
# component. Re-derive on each launcher run and update only when content drifted
# so a deliberately replaced private key cannot leave a stale verifier behind.
function New-JwtRs256PublicKey {
    param(
        [string]$PrivateKeyPath = ".secrets/jwt_rs256.pem",
        [string]$OutputPath = ".secrets/jwt_rs256.pub.pem",
        [switch]$NoDockerFallback
    )

    $absolutePrivateKeyPath = Resolve-StatePath -Path $PrivateKeyPath
    $absoluteOutputPath = Resolve-StatePath -Path $OutputPath

    if (-not (Test-Path $absolutePrivateKeyPath)) {
        throw "Cannot derive public key: private key not found at $PrivateKeyPath. Run New-JwtRs256Key first."
    }

    Write-Status "Deriving RSA-2048 public key from $PrivateKeyPath..."

    $publicPem = $null
    try {
        # Path A: .NET 8 native - RSA.ImportFromPem + ExportSubjectPublicKeyInfoPem
        $privatePem = [System.IO.File]::ReadAllText($absolutePrivateKeyPath)
        $rsa = [System.Security.Cryptography.RSA]::Create()
        try {
            $rsa.ImportFromPem($privatePem)
            $publicPem = $rsa.ExportSubjectPublicKeyInfoPem()
        } finally {
            $rsa.Dispose()
        }
    } catch {
        # Path B: host openssl fallback (requires openssl in PATH)
        if (Get-Command openssl -ErrorAction SilentlyContinue) {
            $publicPem = openssl rsa -in $absolutePrivateKeyPath -pubout 2>&1 | Out-String
            if ($LASTEXITCODE -ne 0) {
                $publicPem = $null
            }
        }

        # Path C: docker fallback (mounts .secrets dir and runs openssl rsa -pubout)
        if (-not $publicPem -and -not $NoDockerFallback -and
            (Get-Command docker -ErrorAction SilentlyContinue)) {
            $secretDirAbs = Split-Path $absolutePrivateKeyPath -Parent
            $privKeyFile = Split-Path $absolutePrivateKeyPath -Leaf
            $publicPem = docker run --rm -v "${secretDirAbs}:/secrets:ro" $OpenSslFallbackImage sh -c "apk add --no-cache openssl >/dev/null 2>&1; openssl rsa -in /secrets/${privKeyFile} -pubout 2>/dev/null" 2>&1 | Out-String
            if ($LASTEXITCODE -ne 0 -or $publicPem -notmatch "BEGIN PUBLIC KEY") {
                $publicPem = $null
            }
        }
    }

    if (-not $publicPem) {
        throw "Failed to derive RSA public key - neither .NET, host openssl, nor docker openssl succeeded."
    }

    $publicPem = $publicPem.Trim()
    if (Test-Path -LiteralPath $absoluteOutputPath) {
        $existingPublicPem = [System.IO.File]::ReadAllText($absoluteOutputPath).Trim()
        if ($existingPublicPem -ceq $publicPem) {
            Write-Ok "RSA-2048 public key at $OutputPath is current (idempotent skip)"
            return
        }
        Write-Warn "RSA public key at $OutputPath does not match the private key; updating"
    }

    [System.IO.File]::WriteAllText(
        $absoluteOutputPath,
        $publicPem,
        [System.Text.UTF8Encoding]::new($false)
    )
    Set-LiveStandPrivateFileMode -Path $absoluteOutputPath

    Write-Ok "Derived RSA-2048 public key at $OutputPath"
}

# Wave 141 SW4: helper for base64url encoding (JWT spec). Used by
# New-TemporalServiceToken below. Generic enough to share with future helpers.
function ConvertTo-Base64Url {
    param([Parameter(Mandatory=$true)][byte[]]$Bytes)
    return [System.Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function ConvertFrom-Base64Url {
    param([Parameter(Mandatory=$true)][string]$Value)
    $padded = $Value.Replace('-', '+').Replace('_', '/')
    switch ($padded.Length % 4) {
        2 { $padded += '==' }
        3 { $padded += '=' }
        1 { throw "Invalid base64url value" }
    }
    return [System.Convert]::FromBase64String($padded)
}

function Test-TemporalServiceToken {
    param(
        [Parameter(Mandatory=$true)][string]$Token,
        [Parameter(Mandatory=$true)][string]$PrivateKeyPath,
        [Parameter(Mandatory=$true)][string]$Subject,
        [Parameter(Mandatory=$true)][string]$Audience,
        [int]$MinimumValiditySeconds = 604800
    )

    try {
        $parts = $Token.Trim().Split('.')
        if ($parts.Count -ne 3) { return $false }

        $headerJson = [System.Text.Encoding]::UTF8.GetString((ConvertFrom-Base64Url $parts[0]))
        $payloadJson = [System.Text.Encoding]::UTF8.GetString((ConvertFrom-Base64Url $parts[1]))
        $header = $headerJson | ConvertFrom-Json
        $payload = $payloadJson | ConvertFrom-Json
        $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

        if ($header.alg -ne 'RS256' -or $header.kid -ne 'primary') { return $false }
        if ($payload.sub -ne $Subject -or $payload.aud -ne $Audience) { return $false }
        if (-not $payload.jti -or $null -eq $payload.iat -or $null -eq $payload.exp) { return $false }
        if ([long]$payload.iat -gt ($now + 60)) { return $false }
        if ([long]$payload.exp -le ($now + $MinimumValiditySeconds)) { return $false }

        $pem = [System.IO.File]::ReadAllText($PrivateKeyPath)
        $rsa = [System.Security.Cryptography.RSA]::Create()
        try {
            $rsa.ImportFromPem($pem)
            $signedBytes = [System.Text.Encoding]::UTF8.GetBytes("$($parts[0]).$($parts[1])")
            $signature = ConvertFrom-Base64Url $parts[2]
            return $rsa.VerifyData(
                $signedBytes,
                $signature,
                [System.Security.Cryptography.HashAlgorithmName]::SHA256,
                [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
            )
        } finally {
            $rsa.Dispose()
        }
    } catch {
        return $false
    }
}

# Wave 141 SW4: mint long-lived service token (~1 year exp) signed with the
# same RSA private key backend uses for its JWTs. Token has sub=
# file-processor-service + aud=temporal claims so Temporal's default JWT claim
# mapper (W141 SW2 verified - common/authorization/default_jwt_claim_mapper.go)
# recognizes it via the JWKS endpoint at /.well-known/jwks.json.
#
# Closes W137 sec.Honesty #5 + W140 NEW #6 (joined with SW3 image swap + SW5 Go
# credentials attach to form the full Path (a-auth) chain).
#
# Idempotent: keeps an existing token only after its claims, lifetime, algorithm,
# and RSA signature have been validated. Invalid or near-expiry tokens are
# replaced automatically.
#
# Security framing: this is a STATIC long-lived service token (no rotation).
# Acceptable for dev compose where the threat model is "anyone with host
# filesystem access". Production K8s deployments use managed Temporal Cloud /
# Helm chart with proper rotation infrastructure - this token NEVER ships to
# production.
#
# Issue temporalio/temporal#8218 mitigation: subject claim name is hardcoded
# as "sub" in default_jwt_claim_mapper.go:19. We mint with sub=
# file-processor-service to match this hardcoded expectation.
function New-TemporalServiceToken {
    param(
        [string]$PrivateKeyPath = ".secrets/jwt_rs256.pem",
        [string]$OutputPath = ".secrets/temporal_api_key",
        [string]$Subject = "file-processor-service",
        [string]$Audience = "temporal",
        [int]$ExpirationSeconds = 31536000, # 1 year (dev-only)
        [switch]$NoDockerFallback
    )

    $absoluteOutputPath = Resolve-StatePath -Path $OutputPath
    $absolutePrivateKeyPath = Resolve-StatePath -Path $PrivateKeyPath
    if (-not (Test-Path $absolutePrivateKeyPath)) {
        throw "Cannot mint Temporal service token: private key not found at $PrivateKeyPath. Run New-JwtRs256Key first."
    }

    if (Test-Path $absoluteOutputPath) {
        $existingToken = [System.IO.File]::ReadAllText($absoluteOutputPath).Trim()
        if (Test-TemporalServiceToken -Token $existingToken -PrivateKeyPath $absolutePrivateKeyPath -Subject $Subject -Audience $Audience) {
            Write-Ok "Valid existing Temporal service token at $OutputPath (idempotent skip)"
            return
        }
        Write-Warn "Temporal service token at $OutputPath is invalid or near expiry; regenerating"
        Remove-Item -LiteralPath $absoluteOutputPath -Force
    }

    $days = [Math]::Round($ExpirationSeconds / 86400)
    Write-Status "Minting Temporal service token (sub=$Subject, aud=$Audience, $days days valid)..."

    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $exp = $now + $ExpirationSeconds
    $jti = [Guid]::NewGuid().ToString("N")
    $headerObj  = [PSCustomObject]@{ alg = 'RS256'; kid = 'primary'; typ = 'JWT' }
    $payloadObj = [PSCustomObject]@{
        sub = $Subject
        aud = $Audience
        iat = $now
        exp = $exp
        jti = $jti
    }

    $headerJson  = $headerObj  | ConvertTo-Json -Compress
    $payloadJson = $payloadObj | ConvertTo-Json -Compress

    $headerB64  = ConvertTo-Base64Url ([System.Text.Encoding]::UTF8.GetBytes($headerJson))
    $payloadB64 = ConvertTo-Base64Url ([System.Text.Encoding]::UTF8.GetBytes($payloadJson))

    $signingInput = "$headerB64.$payloadB64"

    $signatureB64 = $null
    try {
        # Path A: .NET 8 native - RSA.ImportFromPem + SignData
        $pem = [System.IO.File]::ReadAllText($absolutePrivateKeyPath)
        $rsa = [System.Security.Cryptography.RSA]::Create()
        try {
            $rsa.ImportFromPem($pem)
            $signingInputBytes = [System.Text.Encoding]::UTF8.GetBytes($signingInput)
            $signatureBytes    = $rsa.SignData(
                $signingInputBytes,
                [System.Security.Cryptography.HashAlgorithmName]::SHA256,
                [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
            )
            $signatureB64 = ConvertTo-Base64Url $signatureBytes
        } finally {
            $rsa.Dispose()
        }
    } catch {
        # Path B: host openssl fallback (requires openssl in PATH)
        if (Get-Command openssl -ErrorAction SilentlyContinue) {
            $tempInputFile = [System.IO.Path]::GetTempFileName()
            $tempSigFile   = [System.IO.Path]::GetTempFileName()
            try {
                [System.IO.File]::WriteAllText($tempInputFile, $signingInput, [System.Text.Encoding]::UTF8)
                $null = openssl dgst -sha256 -sign $absolutePrivateKeyPath -out $tempSigFile $tempInputFile 2>&1
                if ($LASTEXITCODE -eq 0 -and (Test-Path $tempSigFile)) {
                    $signatureBytes = [System.IO.File]::ReadAllBytes($tempSigFile)
                    $signatureB64   = ConvertTo-Base64Url $signatureBytes
                }
            } finally {
                Remove-Item $tempInputFile, $tempSigFile -ErrorAction SilentlyContinue
            }
        }

        # Path C: docker fallback (runs openssl in alpine container)
        if (-not $signatureB64 -and -not $NoDockerFallback -and
            (Get-Command docker -ErrorAction SilentlyContinue)) {
            $secretDirAbs = Split-Path $absolutePrivateKeyPath -Parent
            $privKeyFile  = Split-Path $absolutePrivateKeyPath -Leaf
            $sigOut = docker run --rm -v "${secretDirAbs}:/secrets:ro" $OpenSslFallbackImage sh -c "apk add --no-cache openssl >/dev/null 2>&1; printf '%s' '$signingInput' | openssl dgst -sha256 -sign /secrets/${privKeyFile} 2>/dev/null | base64 | tr -d '\r\n' | tr '+/' '-_' | tr -d '='" 2>&1 | Out-String
            if ($LASTEXITCODE -eq 0 -and $sigOut.Trim()) {
                $signatureB64 = $sigOut.Trim()
            }
        }
    }

    if (-not $signatureB64) {
        throw "Failed to sign Temporal service token - neither .NET, host openssl, nor docker openssl succeeded."
    }

    $token = "$signingInput.$signatureB64"

    [System.IO.File]::WriteAllText(
        $absoluteOutputPath,
        $token,
        [System.Text.UTF8Encoding]::new($false)
    )
    Set-LiveStandPrivateFileMode -Path $absoluteOutputPath

    Write-Ok "Generated Temporal service token at $OutputPath ($days days valid)"
}

function Assert-PreparedLiveStandConfiguration {
    # The owner will render and sign the resolved Compose volume projection
    # after this phase. Validate local inputs without emitting their contents.
    foreach ($path in @($EnvFile, $EnvCompose, $WorkerEnvFile)) {
        $absolutePath = Resolve-StatePath -Path $path
        if (-not (Test-Path -LiteralPath $absolutePath -PathType Leaf)) {
            throw "Live-stand environment preparation did not create a required file."
        }
    }

    $requiredKeys = @(
        "POSTGRES_PASSWORD", "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD",
        "ELASTIC_PASSWORD", "NATS_USER", "NATS_PASSWORD",
        "SPICEDB_PRESHARED_KEY", "WS_HUB_INTERNAL_SECRET",
        "GRAFANA_ADMIN_PASSWORD", "REDIS_PASSWORD",
        "REVOCATION_REDIS_PASSWORD", "SECRET_KEY", "INTERNAL_HMAC_SECRET",
        "METRICS_BASIC_AUTH_PASSWORD", "IMGPROXY_KEY", "IMGPROXY_SALT",
        "VAPID_SUBJECT"
    )
    $invalidKeys = @()
    foreach ($key in $requiredKeys) {
        $dockerValue = Get-EnvEntry -Path $EnvFile -Key $key
        $composeValue = Get-EnvEntry -Path $EnvCompose -Key $key
        if ([string]::IsNullOrWhiteSpace($dockerValue) -or
            $composeValue -cne $dockerValue) {
            $invalidKeys += $key
        }
    }
    if ($invalidKeys.Count -gt 0) {
        throw "Live-stand environment is incomplete or unsynchronized: $($invalidKeys -join ', ')"
    }

    $workerEnvironment = [System.IO.File]::ReadAllText(
        (Resolve-StatePath -Path $WorkerEnvFile)
    )
    if ($workerEnvironment -match '(?m)^\s*REVOCATION_REDIS_(?:URL|PASSWORD)=') {
        throw "Live-stand worker environment contains a forbidden revocation credential."
    }
    if (-not (Test-JwtRs256PrivateKey -Path (Join-Path $StateRoot ".secrets/jwt_rs256.pem")) -or
        -not (Test-Path -LiteralPath (Join-Path $StateRoot ".secrets/jwt_rs256.pub.pem") -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $StateRoot ".secrets/temporal_api_key") -PathType Leaf)) {
        throw "Live-stand signing configuration is incomplete or invalid."
    }
}

function Test-ServiceHttp {
    param([string]$Url, [int]$Timeout = 2)
    try { (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $Timeout).StatusCode -eq 200 }
    catch { $false }
}

function Get-LocalServiceUrl {
    param([string]$Name, [int]$DefaultPort, [string]$Path)

    $environmentName = if ($Name -ieq "MAILPIT") {
        "LIVE_MAILPIT_PORT"
    } else {
        "LIVE_HOST_PORT_$Name"
    }
    $configuredPort = [Environment]::GetEnvironmentVariable($environmentName)
    $port = $DefaultPort
    if (-not [string]::IsNullOrWhiteSpace($configuredPort)) {
        $parsedPort = 0
        if (-not [int]::TryParse($configuredPort, [ref]$parsedPort) -or $parsedPort -lt 1024 -or $parsedPort -gt 65535) {
            throw "Invalid loopback port in $environmentName."
        }
        $port = $parsedPort
    }

    return "http://localhost:$($port)$Path"
}

function Wait-PrometheusTargets {
    param([int]$Timeout = 75)

    # Storage runs on SeaweedFS, which has no scrape job yet (ADR-042).
    $expectedJobs = @(
        "prometheus", "backend", "notifications-worker", "redis-exporter",
        "tempo", "loki", "pyroscope", "gateway", "flagd"
    )
    $deadline = (Get-Date).AddSeconds($Timeout)
    $lastProblems = @("Prometheus target API has not responded yet")

    do {
        try {
            $response = Invoke-RestMethod `
                -Uri (Get-LocalServiceUrl -Name PROMETHEUS -DefaultPort 9090 -Path "/api/v1/targets?state=active") `
                -TimeoutSec 5
            $targets = @($response.data.activeTargets)
            $lastProblems = @()

            foreach ($job in $expectedJobs) {
                $jobTargets = @($targets | Where-Object { $_.labels.job -eq $job })
                if ($jobTargets.Count -eq 0) {
                    $lastProblems += "${job}: missing target"
                    continue
                }
                foreach ($target in $jobTargets) {
                    if ($target.health -ne "up") {
                        $reason = if ($target.lastError) { $target.lastError } else { "health=$($target.health)" }
                        $lastProblems += "${job}: $reason"
                    }
                }
            }

            if ($lastProblems.Count -eq 0) { return $true }
        } catch {
            $lastProblems = @("Prometheus target API: $($_.Exception.Message)")
        }
        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $deadline)

    foreach ($problem in $lastProblems) { Write-Err "  $problem" }
    return $false
}

function Assert-ManagedComposeVolumeOwnership {
    param([Parameter(Mandatory)][object]$ComposeModel)

    # Compose's automatic volume prefix is not an ownership proof. Check the
    # exact resolved names and labels before build/up can create or reuse them.
    $projectName = $ComposeModel.name
    if (-not ($projectName -is [string]) -or
        [string]::IsNullOrWhiteSpace($projectName)) {
        throw "Resolved Compose configuration has no valid project identity."
    }
    $isLiveStand = @($ExtraCompose).Count -eq 1 -and
        $ExtraCompose[0] -ceq "docker-compose.live.yml"
    if ($isLiveStand -and ($env:COMPOSE_PROJECT_NAME -cne $projectName -or
        $projectName -cnotmatch '^ue-live-[0-9a-f]{16}$')) {
        throw "Resolved Compose project does not match the owned live stand."
    }
    if (-not $isLiveStand -and $projectName -cne "university_ecosystem") {
        throw "Resolved Compose project does not match the repository's default project."
    }
    if ($AllowExistingOwnedVolumes -and -not $isLiveStand) {
        throw "Existing owned volumes are allowed only for the live stand overlay."
    }

    $volumeProperty = $ComposeModel.PSObject.Properties["volumes"]
    $serviceProperty = $ComposeModel.PSObject.Properties["services"]
    if ($null -eq $volumeProperty -or $null -eq $volumeProperty.Value -or
        $null -eq $serviceProperty -or $null -eq $serviceProperty.Value) {
        throw "Resolved Compose volume or service inventory is invalid."
    }

    $managedVolumes = @()
    $resolvedNames = @{}
    foreach ($definitionProperty in $volumeProperty.Value.PSObject.Properties) {
        $volumeKey = [string]$definitionProperty.Name
        $definition = $definitionProperty.Value
        if ([string]::IsNullOrWhiteSpace($volumeKey) -or $null -eq $definition) {
            throw "Resolved Compose volume inventory is invalid."
        }
        $externalProperty = $definition.PSObject.Properties["external"]
        $isExternal = $false
        if ($null -ne $externalProperty) {
            if ($externalProperty.Value -isnot [bool]) {
                throw "Resolved Compose volume ownership is ambiguous."
            }
            $isExternal = [bool]$externalProperty.Value
        }
        if ($isExternal) { continue }

        $nameProperty = $definition.PSObject.Properties["name"]
        $resolvedName = if ($null -ne $nameProperty -and
            -not [string]::IsNullOrWhiteSpace([string]$nameProperty.Value)) {
            [string]$nameProperty.Value
        } else {
            "${projectName}_$volumeKey"
        }
        if ($resolvedName -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]*$' -or
            -not $resolvedName.StartsWith("${projectName}_", [StringComparison]::Ordinal)) {
            throw "Resolved Compose volume is outside the owned project namespace."
        }
        if ($resolvedNames.ContainsKey($resolvedName)) {
            throw "Multiple Compose volumes resolve to one managed resource."
        }
        $resolvedNames[$resolvedName] = $true
        $managedVolumes += [pscustomobject]@{
            Key = $volumeKey
            Name = $resolvedName
        }
    }

    foreach ($service in $serviceProperty.Value.PSObject.Properties) {
        $serviceModel = $service.Value
        if ($null -eq $serviceModel) {
            throw "Resolved Compose service inventory is invalid."
        }
        $volumesFromProperty = $serviceModel.PSObject.Properties["volumes_from"]
        if ($null -ne $volumesFromProperty -and
            @($volumesFromProperty.Value).Count -gt 0) {
            throw "Compose volumes_from is unsupported for owner-checked startup."
        }
        $mountsProperty = $serviceModel.PSObject.Properties["volumes"]
        if ($null -eq $mountsProperty) { continue }
        foreach ($mount in @($mountsProperty.Value)) {
            if ($null -eq $mount) {
                throw "Resolved Compose mount inventory is invalid."
            }
            if ([string]$mount.type -ceq "volume") {
                $source = [string]$mount.source
                if ([string]::IsNullOrWhiteSpace($source) -or
                    $null -eq $volumeProperty.Value.PSObject.Properties[$source]) {
                    throw "Resolved Compose volume mount is anonymous or undeclared."
                }
            }
        }
    }

    if ($managedVolumes.Count -eq 0) { return }
    $listedVolumes = @(docker volume ls --format '{{.Name}}' 2>$null)
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot inspect Docker volume inventory; refusing to start services."
    }
    $existingNames = @($listedVolumes | ForEach-Object { [string]$_ })
    foreach ($volume in $managedVolumes) {
        if ($existingNames -cnotcontains $volume.Name) { continue }
        if ($isLiveStand -and -not $AllowExistingOwnedVolumes) {
            throw "A resolved live-stand volume already exists; refusing to reuse an unowned resource."
        }

        $labelOutput = @(docker volume inspect --format '{{json .Labels}}' $volume.Name 2>$null)
        $inspectExitCode = $LASTEXITCODE
        if ($inspectExitCode -ne 0) {
            throw "Cannot inspect an existing Compose volume; refusing to start services."
        }
        try {
            $labels = ($labelOutput -join [Environment]::NewLine) | ConvertFrom-Json -ErrorAction Stop
        } catch {
            throw "Existing Compose volume labels are unreadable; refusing to start services."
        }
        if ($null -eq $labels -or
            $null -eq $labels.PSObject.Properties["com.docker.compose.project"] -or
            [string]$labels.'com.docker.compose.project' -cne $projectName -or
            $null -eq $labels.PSObject.Properties["com.docker.compose.volume"] -or
            [string]$labels.'com.docker.compose.volume' -cne $volume.Key) {
            throw "Existing volume does not carry the exact Compose ownership labels."
        }
    }
}

function Assert-ComposeConfiguration {
    # Compose config can contain credentials in its rendered JSON. Capture it
    # only to validate the exact startup model, and never print or persist it.
    Write-Status "Validating Docker Compose configuration..."
    $configOutput = @(docker compose @ComposeArgs --env-file $EnvFile config --format json 2>$null)
    $composeExitCode = $LASTEXITCODE
    if ($composeExitCode -ne 0) {
        throw "Docker Compose configuration validation failed; refusing to start services."
    }
    try {
        $composeModel = ($configOutput -join [Environment]::NewLine) | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "Docker Compose configuration could not be read safely; refusing to start services."
    }
    return $composeModel
}

function Resolve-LiveAcceptanceSelection {
    param(
        [Parameter(Mandatory=$true)][object]$ComposeModel,
        [Parameter(Mandatory=$true)][ValidateSet("full", "core")][string]$Stack
    )
    $servicesProperty = $ComposeModel.PSObject.Properties["services"]
    if ($null -eq $servicesProperty -or $null -eq $servicesProperty.Value) {
        throw "Resolved Compose service inventory is invalid."
    }
    $serviceNames = @($servicesProperty.Value.PSObject.Properties.Name | Sort-Object -CaseSensitive)
    if ($serviceNames.Count -eq 0 -or
        @($serviceNames | Where-Object { $_ -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$' }).Count -gt 0 -or
        @($serviceNames | Sort-Object -Unique -CaseSensitive).Count -ne $serviceNames.Count) {
        throw "Resolved Compose service inventory is invalid."
    }
    if ($Stack -ceq "full") {
        return [pscustomobject]@{ Roots = $serviceNames; Services = $serviceNames }
    }
    foreach ($root in $script:LiveAcceptanceCoreRoots) {
        if ($serviceNames -cnotcontains $root) {
            throw "Reviewed live Core service roots are missing from Compose."
        }
    }

    $selected = [System.Collections.Generic.HashSet[string]]::new(
        [StringComparer]::Ordinal
    )
    $pending = [System.Collections.Generic.List[string]]::new()
    foreach ($root in $script:LiveAcceptanceCoreRoots) { $pending.Add($root) }
    while ($pending.Count -gt 0) {
        $lastIndex = $pending.Count - 1
        $serviceName = $pending[$lastIndex]
        $pending.RemoveAt($lastIndex)
        if (-not $selected.Add($serviceName)) { continue }
        $serviceProperty = $servicesProperty.Value.PSObject.Properties |
            Where-Object { $_.Name -ceq $serviceName } | Select-Object -First 1
        if ($null -eq $serviceProperty -or $null -eq $serviceProperty.Value) {
            throw "Resolved Compose dependency references an unknown service."
        }
        $dependencies = [System.Collections.Generic.List[string]]::new()
        $dependsProperty = $serviceProperty.Value.PSObject.Properties["depends_on"]
        if ($null -ne $dependsProperty -and $null -ne $dependsProperty.Value) {
            if ($dependsProperty.Value -is [System.Collections.IDictionary] -or
                $dependsProperty.Value -is [pscustomobject]) {
                foreach ($dependencyProperty in $dependsProperty.Value.PSObject.Properties) {
                    $dependencies.Add([string]$dependencyProperty.Name)
                }
            } elseif ($dependsProperty.Value -is [array]) {
                foreach ($dependency in $dependsProperty.Value) {
                    if ($dependency -isnot [string]) {
                        throw "Resolved Compose dependency inventory is invalid."
                    }
                    $dependencies.Add($dependency)
                }
            } else {
                throw "Resolved Compose dependency inventory is invalid."
            }
        }
        $networkModeProperty = $serviceProperty.Value.PSObject.Properties["network_mode"]
        if ($null -ne $networkModeProperty -and $null -ne $networkModeProperty.Value) {
            if ($networkModeProperty.Value -isnot [string]) {
                throw "Resolved Compose network mode is invalid."
            }
            $networkMode = [string]$networkModeProperty.Value
            if ($networkMode.StartsWith("service:", [StringComparison]::Ordinal)) {
                $dependencies.Add($networkMode.Substring(8))
            }
        }
        $linksProperty = $serviceProperty.Value.PSObject.Properties["links"]
        if ($null -ne $linksProperty -and $null -ne $linksProperty.Value) {
            foreach ($link in @($linksProperty.Value)) {
                if ($link -isnot [string] -or [string]::IsNullOrWhiteSpace($link)) {
                    throw "Resolved Compose link inventory is invalid."
                }
                $dependencies.Add($link.Split([char]":")[0])
            }
        }
        foreach ($dependency in $dependencies) {
            if ([string]::IsNullOrWhiteSpace($dependency) -or
                $serviceNames -cnotcontains $dependency) {
                throw "Resolved Compose dependency references an unknown service."
            }
            if (-not $selected.Contains($dependency)) { $pending.Add($dependency) }
        }
    }
    $selectedNames = @($selected | Sort-Object -CaseSensitive)
    if ($selectedNames.Count -ne $script:LiveAcceptanceCoreClosure.Count) {
        throw "Resolved live Core dependency closure differs from reviewed services."
    }
    for ($index = 0; $index -lt $selectedNames.Count; $index++) {
        if ([string]$selectedNames[$index] -cne [string]$script:LiveAcceptanceCoreClosure[$index]) {
            throw "Resolved live Core dependency closure differs from reviewed services."
        }
    }
    return [pscustomobject]@{
        Roots = @($script:LiveAcceptanceCoreRoots | Sort-Object -CaseSensitive)
        Services = $selectedNames
    }
}

function Get-CommonGitOwnerKeyPath {
    $gitCommonOutput = @()
    try {
        $gitCommonOutput = @(& git -C $ProjectRoot rev-parse --git-common-dir 2>$null)
        $gitExitCode = $LASTEXITCODE
    } catch {
        throw "Live acceptance Git metadata cannot be validated."
    }
    if ($gitExitCode -ne 0 -or $gitCommonOutput.Count -ne 1 -or
        [string]::IsNullOrWhiteSpace([string]$gitCommonOutput[0])) {
        throw "Live acceptance Git metadata cannot be validated."
    }
    $reportedDirectory = [string]$gitCommonOutput[0]
    if ($reportedDirectory -cne $reportedDirectory.Trim() -or
        $reportedDirectory.Contains([char]0)) {
        throw "Live acceptance Git metadata cannot be validated."
    }
    try {
        $commonDirectoryInput = if ([System.IO.Path]::IsPathRooted($reportedDirectory)) {
            $reportedDirectory
        } else {
            Join-Path $ProjectRoot $reportedDirectory
        }
        $commonDirectory = [System.IO.Path]::GetFullPath($commonDirectoryInput)
        if (-not (Test-Path -LiteralPath $commonDirectory -PathType Container)) {
            throw "missing"
        }
        $current = $commonDirectory
        while ($current) {
            $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
            if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                throw "reparse"
            }
            $parent = [System.IO.Path]::GetDirectoryName($current)
            if (-not $parent -or $parent -ceq $current) { break }
            $current = $parent
        }
        return [System.IO.Path]::GetFullPath(
            (Join-Path $commonDirectory "live-stand-owner.key")
        )
    } catch {
        throw "Live acceptance Git metadata path is missing or unsafe."
    }
}

function Get-VerifiedLiveAcceptanceOwner {
    if ($null -ne $script:LiveStandOwner) { return $script:LiveStandOwner }
    if ($LiveStateMode) {
        throw "Live acceptance state owner has not been validated."
    }
    $ownerPath = Join-Path $ProjectRoot ".secrets/live-stand.json"
    $keyPath = Get-CommonGitOwnerKeyPath
    $secretsPath = Join-Path $ProjectRoot ".secrets"
    if (-not (Test-Path -LiteralPath $secretsPath -PathType Container) -or
        ((Get-Item -LiteralPath $secretsPath -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw "Live acceptance owner directory is missing or unsafe."
    }
    foreach ($path in @($ownerPath, $keyPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Live acceptance requires a signed owner marker and key."
        }
        $item = Get-Item -LiteralPath $path -Force
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw "Live acceptance owner paths refuse reparse points."
        }
    }
    try {
        $owner = [System.IO.File]::ReadAllText($ownerPath) |
            ConvertFrom-Json -AsHashtable -ErrorAction Stop
        $key = [System.IO.File]::ReadAllBytes($keyPath)
    } catch {
        throw "Live acceptance owner metadata cannot be validated."
    }
    if ($owner.version -ne 8 -or
        [string]$owner.worktree -ine $ProjectRoot -or
        [string]::IsNullOrWhiteSpace([string]$owner.repository) -or
        [string]$owner.project_name -cnotmatch '^ue-live-[0-9a-f]{16}$' -or
        [string]$owner.stack -cnotin @("full", "core") -or
        -not (Test-CanonicalLiveServiceList -Value $owner.service_roots) -or
        -not (Test-CanonicalLiveServiceList -Value $owner.selected_services) -or
        [string]$owner.compose_resource_fingerprint -cnotmatch '^[0-9a-f]{64}$' -or
        [string]$env:COMPOSE_PROJECT_NAME -cne [string]$owner.project_name -or
        $key.Length -ne 32 -or
        [string]$owner.signature -cnotmatch '^[0-9a-f]{64}$') {
        [Array]::Clear($key, 0, $key.Length)
        throw "Live acceptance owner does not match this worktree and Compose project."
    }
    $payload = [ordered]@{}
    foreach ($name in ($owner.Keys | Where-Object { $_ -cne "signature" } | Sort-Object -CaseSensitive)) {
        $payload[$name] = $owner[$name]
    }
    $hmac = [System.Security.Cryptography.HMACSHA256]::new($key)
    try {
        $actualSignature = [Convert]::ToHexString(
            $hmac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes(
                (ConvertTo-CanonicalLiveOwnerJson -Value $payload)
            ))
        ).ToLowerInvariant()
    } finally {
        $hmac.Dispose()
        [Array]::Clear($key, 0, $key.Length)
    }
    if (-not [System.Security.Cryptography.CryptographicOperations]::FixedTimeEquals(
        [Convert]::FromHexString([string]$owner.signature),
        [Convert]::FromHexString($actualSignature)
    )) {
        throw "Live acceptance owner signature is invalid."
    }
    $script:LiveStandOwner = $owner
    return $owner
}

function Get-LiveAcceptanceVolumeProjection {
    param(
        [Parameter(Mandatory=$true)][object]$ComposeModel,
        [Parameter(Mandatory=$true)][string[]]$SelectedServices
    )
    $selectedSet = [System.Collections.Generic.HashSet[string]]::new(
        [StringComparer]::Ordinal
    )
    foreach ($service in $SelectedServices) { [void]$selectedSet.Add($service) }
    $serviceProperty = $ComposeModel.PSObject.Properties["services"]
    $volumeProperty = $ComposeModel.PSObject.Properties["volumes"]
    if ($null -eq $serviceProperty -or $null -eq $volumeProperty) {
        throw "Resolved Compose service or volume inventory is invalid."
    }
    $filteredServices = [ordered]@{}
    $usedVolumes = [System.Collections.Generic.HashSet[string]]::new(
        [StringComparer]::Ordinal
    )
    foreach ($property in $serviceProperty.Value.PSObject.Properties) {
        if (-not $selectedSet.Contains([string]$property.Name)) { continue }
        $filteredServices[[string]$property.Name] = $property.Value
        $mountsProperty = $property.Value.PSObject.Properties["volumes"]
        if ($null -eq $mountsProperty) { continue }
        foreach ($mount in @($mountsProperty.Value)) {
            if ($null -ne $mount -and [string]$mount.type -ceq "volume") {
                if ([string]::IsNullOrWhiteSpace([string]$mount.source)) {
                    throw "Resolved Compose volume mount is anonymous or undeclared."
                }
                [void]$usedVolumes.Add([string]$mount.source)
            }
        }
    }
    if ($filteredServices.Count -ne $selectedSet.Count) {
        throw "Resolved Compose service projection differs from signed selection."
    }
    $filteredVolumes = [ordered]@{}
    foreach ($property in $volumeProperty.Value.PSObject.Properties) {
        if ($usedVolumes.Contains([string]$property.Name)) {
            $filteredVolumes[[string]$property.Name] = $property.Value
        }
    }
    if ($filteredVolumes.Count -ne $usedVolumes.Count) {
        throw "Resolved Compose service references an undeclared volume."
    }
    return [pscustomobject]@{
        name = $ComposeModel.name
        services = [pscustomobject]$filteredServices
        volumes = [pscustomobject]$filteredVolumes
    }
}

function Assert-LiveAcceptanceSelection {
    param([Parameter(Mandatory=$true)][object]$ComposeModel)
    if ([string]::IsNullOrEmpty($LiveAcceptanceStack) -and
        [string]::IsNullOrEmpty($LiveAcceptanceServicesJson)) {
        if ($LiveStateMode) {
            $existingOwner = Get-VerifiedLiveAcceptanceOwner
            if ([string]$existingOwner.stack -ceq "core") {
                throw "A Core-owned live stand requires its signed stack selection on startup."
            }
        } elseif (@($ExtraCompose).Count -eq 1 -and
            $ExtraCompose[0] -ceq "docker-compose.live.yml" -and
            (Test-Path -LiteralPath (Join-Path $ProjectRoot ".secrets/live-stand.json") -PathType Leaf)) {
            $existingOwner = Get-VerifiedLiveAcceptanceOwner
            if ([string]$existingOwner.stack -ceq "core") {
                throw "A Core-owned live stand requires its signed stack selection on startup."
            }
        }
        return $false
    }
    if (-not $LiveStateMode -and
        (@($ExtraCompose).Count -ne 1 -or
            $ExtraCompose[0] -cne "docker-compose.live.yml")) {
        throw "Live acceptance stack selection requires the owned live overlay."
    }
    if ($Core) {
        throw "Live acceptance stack selection cannot be combined with legacy -Core."
    }
    if ($LiveAcceptanceStack -cnotin @("full", "core") -or
        [string]::IsNullOrEmpty($LiveAcceptanceServicesJson)) {
        throw "Live acceptance requires both a fixed stack and its signed service selection."
    }
    try {
        $callerServices = ConvertFrom-Json -InputObject $LiveAcceptanceServicesJson `
            -AsHashtable -ErrorAction Stop
    } catch {
        throw "Live acceptance service selection is invalid."
    }
    if (-not (Test-CanonicalLiveServiceList -Value $callerServices)) {
        throw "Live acceptance service selection is not a sorted unique service list."
    }
    $selection = Resolve-LiveAcceptanceSelection -ComposeModel $ComposeModel `
        -Stack $LiveAcceptanceStack
    $services = [string[]]$selection.Services
    $roots = [string[]]$selection.Roots
    if (@($callerServices).Count -ne $services.Count) {
        throw "Caller live service selection differs from resolved Compose closure."
    }
    for ($index = 0; $index -lt $services.Count; $index++) {
        if ([string]$callerServices[$index] -cne [string]$services[$index]) {
            throw "Caller live service selection differs from resolved Compose closure."
        }
    }
    $owner = Get-VerifiedLiveAcceptanceOwner
    if ([string]$owner.stack -cne $LiveAcceptanceStack -or
        [string]$owner.compose_resource_fingerprint -cnotmatch '^[0-9a-f]{64}$' -or
        @($owner.service_roots).Count -ne $roots.Count -or
        @($owner.selected_services).Count -ne $services.Count) {
        throw "Live acceptance selection differs from signed stand ownership."
    }
    for ($index = 0; $index -lt $roots.Count; $index++) {
        if ([string]$owner.service_roots[$index] -cne [string]$roots[$index]) {
            throw "Live acceptance roots differ from signed stand ownership."
        }
    }
    for ($index = 0; $index -lt $services.Count; $index++) {
        if ([string]$owner.selected_services[$index] -cne [string]$services[$index]) {
            throw "Live acceptance services differ from signed stand ownership."
        }
    }
    $script:LiveAcceptanceRoots = $roots
    $script:LiveAcceptanceServices = $services
    return $true
}

function Assert-LiveComposeVersion {
    if (-not $LiveStateMode) { return }
    $versionOutput = @(docker compose version --short 2>$null)
    $versionExitCode = $LASTEXITCODE
    $versionText = ($versionOutput -join " ").Trim()
    if ($versionExitCode -ne 0 -or
        $versionText -notmatch '^v?(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)') {
        throw "Cannot determine Docker Compose version required by the live override."
    }
    $major = [int]$Matches.major
    $minor = [int]$Matches.minor
    $patch = [int]$Matches.patch
    if ($major -lt 2 -or ($major -eq 2 -and
        ($minor -lt 24 -or ($minor -eq 24 -and $patch -lt 4)))) {
        throw "In-place live stands require Docker Compose 2.24.4 or newer for !override."
    }
}

# -- Prerequisite: Docker running ---------------------------------------------

if (-not $PrepareOnly) {
    Write-Status "Checking Docker..."
    $dockerOk = $false
    try {
        $null = docker info 2>$null
        $dockerOk = $LASTEXITCODE -eq 0
    } catch { }

    if (-not $dockerOk) {
        Write-Err "Docker is not running. Start Docker Desktop and try again."
        exit 1
    }
}

if (-not $PrepareOnly) { Assert-LiveComposeVersion }

# -- Handle -Down -------------------------------------------------------------

if ($Down) {
    if (@($ExtraCompose).Count -gt 0) {
        throw "-Down only targets the default Compose project; use scripts/live_stand.py for an owned live stand."
    }
    Write-Status "Stopping all containers..."
    $envArgs = if (Test-Path $EnvFile) { @("--env-file", $EnvFile) } else { @() }
    # Pin this destructive command to the repository's declared default
    # project. A process or .env.docker COMPOSE_PROJECT_NAME override must not
    # redirect -Down to an unrelated Compose project.
    docker compose --project-name "university_ecosystem" @ComposeArgs @envArgs down
    $composeExitCode = $LASTEXITCODE
    if ($composeExitCode -ne 0) {
        Write-Err "Failed to stop containers."
        exit $composeExitCode
    }
    Write-Ok "All containers stopped"
    exit $composeExitCode
}

# -- Handle -Logs -------------------------------------------------------------

if ($Logs) {
    $envArgs = if (Test-Path $EnvFile) { @("--env-file", $EnvFile) } else { @() }
    if ($LogService) {
        if ($Core -and $LogService -notin $CoreComposeServices) {
            Write-Err "Core mode only exposes logs for core services. Unknown or optional service: $LogService"
            exit 2
        }
        docker compose @ComposeArgs @envArgs logs -f $LogService
    } elseif ($Core) {
        Write-Status "Following core service logs (optional services are excluded)..."
        docker compose @ComposeArgs @envArgs logs -f @CoreComposeServices
    } else {
        docker compose @ComposeArgs @envArgs logs -f
    }
    $composeExitCode = $LASTEXITCODE
    if ($composeExitCode -ne 0) {
        Write-Err "Failed to read container logs."
    }
    exit $composeExitCode
}

# -- Legacy MinIO volume guard -----------------------------------------------

function Assert-LegacyS3VolumeGuard {
    # SeaweedFS cannot read MinIO's data directory. On a machine that still
    # holds a MinIO volume, the first start would create an empty SeaweedFS
    # volume; after that nothing could tell that legacy objects were left
    # behind. A target name alone cannot show that its contents were verified,
    # so require both the exact project target and a matching durable operator
    # attestation. Runs before environment mutation; legacy data is untouched.
    #
    # Compose project identity is shared with both wrapper guards and the
    # Compose models: environment, .env.docker, then the declared default.
    $composeProject = $env:COMPOSE_PROJECT_NAME
    if ([string]::IsNullOrWhiteSpace($composeProject)) {
        $projectEntry = Get-Content -LiteralPath (Resolve-StatePath -Path $EnvFile) -ErrorAction SilentlyContinue |
            Where-Object { $_ -match '^\s*COMPOSE_PROJECT_NAME\s*=' } |
            Select-Object -Last 1
        if ($projectEntry) {
            $composeProject = ($projectEntry -split '=', 2)[1].Trim().Trim('"', "'")
        }
    }
    if ([string]::IsNullOrWhiteSpace($composeProject)) {
        $composeProject = "university_ecosystem"
    }
    # docker-compose.full.yml named it `minio-data`, docker-compose.yml
    # `minio_data`; both were project-scoped.
    $legacyVolumes = @("${composeProject}_minio-data", "${composeProject}_minio_data")
    $storageVolume = "${composeProject}_seaweedfs_data"

    # List every name and compare exactly: Docker's name filter matches
    # substrings.
    $existing = @(docker volume ls --format "{{.Name}}" 2>$null)
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot inspect Docker volumes; refusing to start object storage without checking for a legacy MinIO volume."
    }
    $legacy = @($legacyVolumes | Where-Object { $existing -ccontains $_ })
    if ($legacy.Count -eq 0) { return }

    $targetExists = $existing -ccontains $storageVolume
    $expectedAttestation = @(
        "schema_version=1",
        "project_name=$composeProject",
        "legacy_source_volumes=$($legacy -join ',')",
        "target_volume=$storageVolume",
        "verified=VERIFIED_S3_CUTOVER"
    )
    $attestationPath = Resolve-StatePath -Path $S3MigrationAttestation
    $attestationMatches = $false
    if (Test-Path -LiteralPath $attestationPath -PathType Leaf) {
        $actualAttestation = @(Get-Content -LiteralPath $attestationPath)
        $attestationMatches = $actualAttestation.Count -eq $expectedAttestation.Count -and
            [string]::Join("`n", $actualAttestation) -ceq [string]::Join("`n", $expectedAttestation)
    }
    if (-not $targetExists -or -not $attestationMatches) {
        throw "Legacy MinIO volume $($legacy -join ', ') exists. Refusing to start unless the exact target volume '$storageVolume' exists and $S3MigrationAttestation records the verified migration. Follow $S3MigrationRunbook first."
    }
    Write-Warn "Verified S3 migration attestation matches project '$composeProject', source '$($legacy -join ', ')', and target '$storageVolume'. Legacy data remains untouched."
}

if (-not $PrepareOnly) {
    Assert-LegacyS3VolumeGuard
}

# -- Generate secrets ---------------------------------------------------------

$generated = $false

$needsEnvDocker = -not (Test-Path $EnvFile)
$needsEnvCompose = -not (Test-Path $EnvCompose)

if ($needsEnvDocker -and $needsEnvCompose) {
    # Both missing - fresh setup, generate from scratch
    Write-Status "Generating environment files with secure secrets..."

    $postgresPassword = New-Secret -Length 32
    $secretKey         = New-Secret -Length 64
    $minioPassword     = New-Secret -Length 32
    $redisPassword     = New-Secret -Length 32
    $revocationRedisPassword = New-Secret -Length 32
    $tokenHmacSecret  = New-Secret -Length 48
    $elasticPassword   = New-Secret -Length 32
    $natsPassword      = New-Secret -Length 32
    $spicedbKey        = New-Secret -Length 32
    $wsHubSecret       = New-Secret -Length 32
    $grafanaPassword   = New-Secret -Length 32
    $metricsPassword   = New-Secret -Length 48
    $imgproxyKey       = New-HexSecret -Length 32
    $imgproxySalt      = New-HexSecret -Length 32
    $csrfHmacSecret    = New-Secret -Length 48
    $internalHmacSecret = New-Secret -Length 48
    $idempotencyHmacSecret = New-Secret -Length 48
    $spotifyTokenSecret = New-FernetKey
    $spotifyOauthStateSecret = New-Secret -Length 48

    # -- .env.docker (container env_file) ---------------------------------
    $dockerEnv = @"
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$postgresPassword
POSTGRES_DB=university
SECRET_KEY=$secretKey
ALGORITHM=RS256
JWT_AUDIENCE=university-ecosystem-api
JWT_ISSUER=university-ecosystem
JWT_PRIVATE_KEY_PATH=.secrets/jwt_rs256.pem
ACCESS_TOKEN_EXPIRE_MINUTES=30
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=$minioPassword
ELASTIC_PASSWORD=$elasticPassword
NATS_USER=app
NATS_PASSWORD=$natsPassword
SPICEDB_PRESHARED_KEY=$spicedbKey
WS_HUB_INTERNAL_SECRET=$wsHubSecret
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$grafanaPassword
REDIS_PASSWORD=$redisPassword
REVOCATION_REDIS_PASSWORD=$revocationRedisPassword
TOKEN_HMAC_SECRET=$tokenHmacSecret
ENABLE_METRICS_ENDPOINT=true
METRICS_BASIC_AUTH_USERNAME=metrics_scraper
METRICS_BASIC_AUTH_PASSWORD=$metricsPassword
IMGPROXY_KEY=$imgproxyKey
IMGPROXY_SALT=$imgproxySalt
IMGPROXY_BASE_URL=http://localhost/imgproxy
VAPID_SUBJECT=mailto:admin@example.com
ENVIRONMENT=development
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=
SPOTIFY_SCOPES=
CSRF_HMAC_SECRET=$csrfHmacSecret
INTERNAL_HMAC_SECRET=$internalHmacSecret
IDEMPOTENCY_HMAC_SECRET=$idempotencyHmacSecret
SPOTIFY_TOKEN_SECRET=$spotifyTokenSecret
SPOTIFY_OAUTH_STATE_SECRET=$spotifyOauthStateSecret
"@
    Write-Utf8NoBom $EnvFile $dockerEnv

    # -- .env (compose interpolation) -------------------------------------
    $composeEnv = @"
# Auto-generated by start-docker.ps1 - used for docker compose interpolation.
# Passwords MUST match .env.docker. Re-run start-docker.ps1 after editing.
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$postgresPassword
POSTGRES_DB=university
SECRET_KEY=$secretKey
ALGORITHM=RS256
JWT_AUDIENCE=university-ecosystem-api
JWT_ISSUER=university-ecosystem
JWT_PRIVATE_KEY_PATH=.secrets/jwt_rs256.pem
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=$minioPassword
ELASTIC_PASSWORD=$elasticPassword
NATS_USER=app
NATS_PASSWORD=$natsPassword
SPICEDB_PRESHARED_KEY=$spicedbKey
WS_HUB_INTERNAL_SECRET=$wsHubSecret
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$grafanaPassword
REDIS_PASSWORD=$redisPassword
REVOCATION_REDIS_PASSWORD=$revocationRedisPassword
TOKEN_HMAC_SECRET=$tokenHmacSecret
ENABLE_METRICS_ENDPOINT=true
METRICS_BASIC_AUTH_USERNAME=metrics_scraper
METRICS_BASIC_AUTH_PASSWORD=$metricsPassword
IMGPROXY_KEY=$imgproxyKey
IMGPROXY_SALT=$imgproxySalt
IMGPROXY_BASE_URL=http://localhost/imgproxy
ENVIRONMENT=development
VAPID_SUBJECT=mailto:admin@example.com
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=
SPOTIFY_SCOPES=
CSRF_HMAC_SECRET=$csrfHmacSecret
INTERNAL_HMAC_SECRET=$internalHmacSecret
IDEMPOTENCY_HMAC_SECRET=$idempotencyHmacSecret
SPOTIFY_TOKEN_SECRET=$spotifyTokenSecret
SPOTIFY_OAUTH_STATE_SECRET=$spotifyOauthStateSecret
"@
    Write-Utf8NoBom $EnvCompose $composeEnv

    Write-Ok "Generated $EnvFile and $EnvCompose with secure secrets"
    $generated = $true
} elseif ($needsEnvDocker -and -not $needsEnvCompose) {
    # .env exists but .env.docker missing - copy .env as base for .env.docker
    Write-Warn ".env.docker missing - deriving from .env..."
    Copy-Item $EnvCompose $EnvFile
    Set-LiveStandPrivateFileMode -Path (Resolve-StatePath -Path $EnvFile)
    Write-Ok "Created $EnvFile from $EnvCompose"
    $generated = $true
} elseif (-not $needsEnvDocker -and $needsEnvCompose) {
    # .env.docker exists but .env missing - derive .env from .env.docker
    Write-Warn ".env missing - deriving from .env.docker..."
    Copy-Item $EnvFile $EnvCompose
    Set-LiveStandPrivateFileMode -Path (Resolve-StatePath -Path $EnvCompose)
    Write-Ok "Created $EnvCompose from $EnvFile"
    $generated = $true
}

# Enable signed imgproxy URLs for both fresh and pre-existing local setups.
Ensure-ImgproxyEnvironment

# Enable authenticated Prometheus scraping for fresh and existing setups.
Ensure-MetricsEnvironment

# Give each application security domain an independent launcher-managed key.
Ensure-ApplicationSecrets

# Fail closed if an existing local configuration reuses the cache password for
# the durable security-state Redis. Fresh generation uses independent CSPRNG
# values; manual rotation requires an explicit distinct replacement.
Assert-IndependentRedisCredentials

# Keep RS256 settings coherent in both supported Compose environment files.
Ensure-JwtEnvironment

# Make bind-mounted configuration changes visible to Compose's config hash.
Ensure-DockerConfigRevision

# Materialize the worker view only after every launcher-managed mutation of
# the canonical .env.docker file, so it cannot become stale during a restart.
# It deliberately denies both the revocation URL and its credential even when
# a user copied every documented value into .env.docker.
Write-WorkerEnvironmentFile

# -- Sync check: keep Compose interpolation in lockstep with .env.docker ------
# Compose reads these values from .env while containers read .env.docker. A
# partially populated or stale .env therefore fails before the backend starts
# (or, worse, starts services with credentials that do not match). Treat the
# docker env file as the canonical source for every required interpolation key,
# including keys that older launcher versions forgot to backfill.
if (-not $generated) {
    $composeSyncKeys = @(
        "POSTGRES_PASSWORD",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
        "ELASTIC_PASSWORD",
        "NATS_USER",
        "NATS_PASSWORD",
        "SPICEDB_PRESHARED_KEY",
        "WS_HUB_INTERNAL_SECRET",
        "GRAFANA_ADMIN_PASSWORD",
        "REDIS_PASSWORD",
        "REVOCATION_REDIS_PASSWORD",
        "SECRET_KEY",
        "INTERNAL_HMAC_SECRET",
        "METRICS_BASIC_AUTH_PASSWORD",
        "IMGPROXY_KEY",
        "IMGPROXY_SALT"
    )
    $missingDockerKeys = @()
    $synchronizedKeys = @()
    foreach ($key in $composeSyncKeys) {
        $dockerValue = Get-EnvEntry -Path $EnvFile -Key $key
        if ([string]::IsNullOrWhiteSpace($dockerValue)) {
            $missingDockerKeys += $key
            continue
        }
        if ((Get-EnvEntry -Path $EnvCompose -Key $key) -ne $dockerValue) {
            Set-EnvEntry -Path $EnvCompose -Key $key -Value $dockerValue
            $synchronizedKeys += $key
        }
    }
    if ($missingDockerKeys.Count -gt 0) {
        throw "Required variables are missing or empty in ${EnvFile}: $($missingDockerKeys -join ', ')"
    }
    if ($synchronizedKeys.Count -gt 0) {
        Write-Ok "Synchronized Compose variables from ${EnvFile}: $($synchronizedKeys -join ', ')"
    }
}

# -- Wave 137 SW1: Generate RSA-2048 keypair for JWT RS256 signing -------------
# Backend reads .secrets/jwt_rs256.pem at startup (jwt_settings.py:202-205).
# Volume-mounted into container at /app/.secrets/jwt_rs256.pem.
New-JwtRs256Key -OutputPath ".secrets/jwt_rs256.pem" -NoDockerFallback:$PrepareOnly

# Derive the public key used directly by file-processor. Temporal obtains the
# same key from backend's JWKS endpoint and now waits for backend readiness, so
# its first authenticated request cannot race an empty key-provider cache.
New-JwtRs256PublicKey -PrivateKeyPath ".secrets/jwt_rs256.pem" -OutputPath ".secrets/jwt_rs256.pub.pem" -NoDockerFallback:$PrepareOnly

# -- Wave 141 SW4: Mint Temporal service token (RS256 JWT) ---------------------
# file-processor (W141 SW5) reads .secrets/temporal_api_key and attaches it to
# Temporal client via client.NewAPIKeyStaticCredentials(token). Temporal's
# default JWT claim mapper (W141 SW2 verified) validates via the JWKS endpoint
# at /.well-known/jwks.json. Existing tokens are retained only after their
# claims, expiry, algorithm, and RSA signature pass validation.
    New-TemporalServiceToken -NoDockerFallback:$PrepareOnly

# These three files are bind-mounted individually into the non-root services
# that consume them. The state root and .secrets directory stay private (0700);
# host users cannot traverse to these 0644 files, while container UIDs can read
# the individual read-only mounts. Ownership, VAPID, and admin files remain 0600.
Set-LiveStandRuntimeSecretFileMode -Path (Resolve-StatePath ".secrets/jwt_rs256.pem")
Set-LiveStandRuntimeSecretFileMode -Path (Resolve-StatePath ".secrets/jwt_rs256.pub.pem")
Set-LiveStandRuntimeSecretFileMode -Path (Resolve-StatePath ".secrets/temporal_api_key")

# -- Wave 137 SW2: SECRET_KEY drift detection .env <-> .env.docker ---------------
# Closes W136 polish-v2 finding: gateway's JWT_SECRET env reads from .env via
# compose's ${SECRET_KEY} substitution, while backend's env_file reads .env.docker.
# If .env's SECRET_KEY drifts (e.g. stale Pydantic placeholder), gateway HS256
# fallback path validates against the wrong secret -> 401 on every request.
# Less critical post-W137 SW1 RS256 (gateway uses JWKS path) but kept for
# defense-in-depth: fallback HS256 path must remain coherent.
if ((Test-Path $EnvFile) -and (Test-Path $EnvCompose)) {
    $envDockerSecret = (Select-String -Path $EnvFile -Pattern "^SECRET_KEY=(.+)$" -ErrorAction SilentlyContinue).Matches.Groups[1].Value
    $envComposeSecret = (Select-String -Path $EnvCompose -Pattern "^SECRET_KEY=(.+)$" -ErrorAction SilentlyContinue).Matches.Groups[1].Value

    if ($envDockerSecret -and $envComposeSecret -and $envDockerSecret -ne $envComposeSecret) {
        Write-Warn "SECRET_KEY drift detected between .env and .env.docker"
        Write-Status "Syncing .env SECRET_KEY to match .env.docker (canonical source)..."

        # Line-based replacement avoids regex special-char hazards in the
        # secret value (which is alphanumeric per New-Secret but defensive).
        $newLine = "SECRET_KEY=$envDockerSecret"
        $envComposeContent = (Get-Content $EnvCompose -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_ -match "^SECRET_KEY=") { $newLine } else { $_ }
        }) -join "`n"

        Write-Utf8NoBom $EnvCompose $envComposeContent.TrimEnd()
        Write-Ok "Synced .env SECRET_KEY (defense-in-depth for HS256 fallback path)"
    }
}

if ($PrepareOnly) {
    Assert-PreparedLiveStandConfiguration
    Write-Ok "Live stand environment prepared for owner fingerprint registration; no services were started."
    exit 0
}

$resolvedComposeModel = Assert-ComposeConfiguration
$hasLiveAcceptanceSelection = Assert-LiveAcceptanceSelection -ComposeModel $resolvedComposeModel
$script:LiveAcceptanceCore = $hasLiveAcceptanceSelection -and
    $LiveAcceptanceStack -ceq "core"
if ($script:LiveAcceptanceCore -and $Core) {
    throw "Live acceptance Core and legacy Core selections cannot be combined."
}
$liveAcceptanceServiceArgs = @($script:LiveAcceptanceServices)
$liveAcceptanceRootArgs = @($script:LiveAcceptanceRoots)
$ownershipComposeModel = $resolvedComposeModel
if ($script:LiveAcceptanceCore) {
    $ownershipComposeModel = Get-LiveAcceptanceVolumeProjection `
        -ComposeModel $resolvedComposeModel `
        -SelectedServices $script:LiveAcceptanceServices
}
Assert-ManagedComposeVolumeOwnership -ComposeModel $ownershipComposeModel

# -- Core resource guard ------------------------------------------------------

function Get-LiveAcceptanceCoreReadinessInventory {
    return [ordered]@{
        backend = @{ type = "docker"; service = "backend"; ready = $false }
        caddy = @{ type = "http"; service = "caddy"; url = (Get-LocalServiceUrl -Name CADDY_HTTP -DefaultPort 80 -Path "/healthz"); ready = $false }
        site = @{ type = "http"; service = "caddy"; url = (Get-LocalServiceUrl -Name CADDY_HTTP -DefaultPort 80 -Path "/login"); timeout = 20; ready = $false }
        flagd = @{ type = "docker"; service = "flagd"; ready = $false }
        flagdHealth = @{ type = "docker"; service = "flagd-healthprobe"; ready = $false }
        frontend = @{ type = "http"; service = "frontend"; url = (Get-LocalServiceUrl -Name FRONTEND -DefaultPort 8081 -Path "/login"); timeout = 20; ready = $false }
        gateway = @{ type = "http"; service = "gateway"; url = (Get-LocalServiceUrl -Name GATEWAY -DefaultPort 8080 -Path "/health"); ready = $false }
        imgproxy = @{ type = "docker"; service = "imgproxy"; ready = $false }
        mailpit = @{ type = "http"; service = "mailpit"; url = (Get-LocalServiceUrl -Name MAILPIT -DefaultPort 8025 -Path "/api/v1/info"); ready = $false }
        migrations = @{ type = "job"; service = "migrations"; ready = $false }
        minio = @{ type = "docker"; service = "minio"; ready = $false }
        minioInit = @{ type = "job"; service = "minio-init"; ready = $false }
        nats = @{ type = "docker"; service = "nats"; ready = $false }
        notifications = @{ type = "docker"; service = "notifications-worker"; ready = $false }
        outbox = @{ type = "docker"; service = "outbox-worker"; ready = $false }
        postgres = @{ type = "docker"; service = "postgres"; ready = $false }
        postgresInit = @{ type = "job"; service = "postgres-databases-init"; ready = $false }
        redis = @{ type = "docker"; service = "redis"; ready = $false }
        revocationRedis = @{ type = "docker"; service = "revocation-redis"; ready = $false }
        spicedb = @{ type = "docker"; service = "spicedb"; ready = $false }
        spicedbMigrate = @{ type = "job"; service = "spicedb-migrate"; ready = $false }
        tempo = @{ type = "docker"; service = "tempo"; ready = $false }
        tempoProbe = @{ type = "docker"; service = "tempo-healthprobe"; ready = $false }
        wshub = @{ type = "http"; service = "ws-hub"; url = (Get-LocalServiceUrl -Name WS_HUB -DefaultPort 8083 -Path "/health"); ready = $false }
    }
}

function Get-StartupReadinessInventory {
    param(
        [switch]$LiveAcceptanceCore,
        [switch]$Core,
        [System.Collections.IDictionary]$CoreReadiness,
        [System.Collections.IDictionary]$FullReadiness
    )

    if ($LiveAcceptanceCore -and $Core) {
        throw "Live acceptance Core and legacy Core selections cannot be combined."
    }
    if ($LiveAcceptanceCore) {
        if ($null -eq $CoreReadiness -or $null -eq $FullReadiness) {
            throw "Readiness inventories are required for live stack selection."
        }
        return $CoreReadiness
    }
    if ($null -eq $FullReadiness) {
        throw "Full-stack readiness inventory is required."
    }
    if ($Core) {
        foreach ($name in $CoreExcludedHealthServices) {
            [void]$FullReadiness.Remove($name)
        }
    }
    return $FullReadiness
}

if ($script:LiveAcceptanceCore) {
    # The live acceptance Core preset has its own complete readiness inventory.
    # One-shot initialization services must have exited successfully; every
    # other selected service is checked directly or through its established
    # live HTTP endpoint. The default/full readiness map above stays unchanged.
    $coreReadiness = Get-LiveAcceptanceCoreReadinessInventory
    $representedCoreServices = @($coreReadiness.Values | ForEach-Object { [string]$_.service } | Sort-Object -Unique -CaseSensitive)
    if ($representedCoreServices.Count -ne $script:LiveAcceptanceServices.Count) {
        throw "Live Core readiness inventory does not cover its signed service closure."
    }
    for ($index = 0; $index -lt $representedCoreServices.Count; $index++) {
        if ([string]$representedCoreServices[$index] -cne [string]$script:LiveAcceptanceServices[$index]) {
            throw "Live Core readiness inventory does not cover its signed service closure."
        }
    }
} elseif ($Core) {
    # Stop optional containers before any build work so Docker Desktop can
    # reclaim their CPU and memory during a potentially expensive image build.
    # `stop` preserves their named volumes and makes switching back to the
    # default full mode lossless; no image, network, or data is deleted here.
    Write-Status "Stopping optional search, Temporal, and observability containers (volumes preserved)..."
    docker compose @ComposeArgs --env-file $EnvFile stop @CoreOptionalComposeServices
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to stop optional containers; refusing to start core mode."
        exit 1
    }
}

# -- Build --------------------------------------------------------------------

if ($Rebuild) {
    if ($script:LiveAcceptanceCore) {
        Write-Status "Rebuilding the owner-bound live Core service closure (no cache)..."
        docker compose @ComposeArgs --env-file $EnvFile build --no-cache @liveAcceptanceServiceArgs
    } elseif ($Core) {
        Write-Status "Rebuilding core images (no cache; optional services are skipped)..."
        docker compose @ComposeArgs --env-file $EnvFile build --no-cache @CoreComposeServices
    } else {
        Write-Status "Rebuilding ALL images (no cache)..."
        docker compose @ComposeArgs --env-file $EnvFile build --no-cache
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Build failed. Check output above."
        exit 1
    }
    Write-Ok $(if ($script:LiveAcceptanceCore) { "Live acceptance Core images rebuilt" } elseif ($Core) { "Core images rebuilt" } else { "All images rebuilt" })
} elseif ($Build) {
    if ($script:LiveAcceptanceCore) {
        Write-Status "Building the owner-bound live Core service closure..."
        docker compose @ComposeArgs --env-file $EnvFile build @liveAcceptanceServiceArgs
    } elseif ($Core) {
        Write-Status "Building core images (cached; optional services are skipped)..."
        docker compose @ComposeArgs --env-file $EnvFile build @CoreComposeServices
    } else {
        Write-Status "Building images (cached)..."
        docker compose @ComposeArgs --env-file $EnvFile build
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Build failed. Check output above."
        exit 1
    }
    Write-Ok $(if ($script:LiveAcceptanceCore) { "Live acceptance Core images built" } elseif ($Core) { "Core images built" } else { "Images built" })
}

# -- Start services -----------------------------------------------------------

if ($script:LiveAcceptanceCore) {
    Write-Status "Starting the signed live Core roots with normal Compose dependencies..."
    docker compose @ComposeArgs --env-file $EnvFile up -d @liveAcceptanceRootArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to start the signed live Core roots."
        docker compose @ComposeArgs --env-file $EnvFile ps --all
        exit 1
    }
} elseif ($Core) {
    # Keep dependency ordering for the core topology. The gateway depends on a
    # Tempo health sidecar in the full model, so it is intentionally started in
    # a final `--no-deps` step after core dependencies are up; no optional
    # service can be pulled in implicitly.
    Write-Status "Starting core infrastructure..."
    docker compose @ComposeArgs --env-file $EnvFile up -d $CoreBootstrapServices
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to start core infrastructure."
        docker compose @ComposeArgs --env-file $EnvFile ps --all
        exit 1
    }

    Write-Status "Starting core database initialization..."
    docker compose @ComposeArgs --env-file $EnvFile up -d $CoreInitServices
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to start core database initialization."
        docker compose @ComposeArgs --env-file $EnvFile ps --all
        docker compose @ComposeArgs --env-file $EnvFile logs --tail=50 postgres postgres-databases-init minio-init migrations spicedb-migrate 2>$null
        exit 1
    }

    Write-Status "Starting core application services..."
    $coreApplicationServices = @(
        "flagd-healthprobe",
        "spicedb",
        "backend",
        "frontend",
        "notifications-worker",
        "outbox-worker",
        "ws-hub",
        "imgproxy"
    )
    docker compose @ComposeArgs --env-file $EnvFile up -d $coreApplicationServices
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to start core application services."
        docker compose @ComposeArgs --env-file $EnvFile ps --all
        docker compose @ComposeArgs --env-file $EnvFile logs --tail=50 backend outbox-worker ws-hub 2>$null
        exit 1
    }

    Write-Status "Starting gateway and Caddy without optional observability dependencies..."
    docker compose @ComposeArgs --env-file $EnvFile up -d --no-deps gateway caddy
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to start the core edge services."
        docker compose @ComposeArgs --env-file $EnvFile ps --all
        docker compose @ComposeArgs --env-file $EnvFile logs --tail=50 gateway caddy 2>$null
        exit 1
    }
} else {
    Write-Status "Starting containers..."
    # Compose recreates only services whose image or effective configuration
    # changed. Do not request automatic orphan removal: a Compose project name
    # is a shared namespace, not proof that an orphan belongs to this run.
    # Retired containers require a separate ownership-reviewed cleanup.
    docker compose @ComposeArgs --env-file $EnvFile up -d
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to start containers."
        docker compose @ComposeArgs --env-file $EnvFile ps --all
        docker compose @ComposeArgs --env-file $EnvFile logs --tail=50 migrations postgres-databases-init minio-init spicedb-migrate temporal-admin-tools temporal-namespace-init flagd flagd-healthprobe backend outbox-worker 2>$null
        exit 1
    }
}

# -- Health check loop --------------------------------------------------------

Write-Status "Waiting for services..."
$timeout = 300
$elapsed = 0
$fullReadiness = [ordered]@{
    postgres      = @{ type = "docker"; service = "postgres"; ready = $false }
    redis         = @{ type = "docker"; service = "redis"; ready = $false }
    redisexporter = @{ type = "docker"; service = "redis-exporter"; ready = $false }
    flagd         = @{ type = "docker"; service = "flagd-healthprobe"; ready = $false }
    backend       = @{ type = "docker"; service = "backend"; ready = $false }
    elasticsearch = @{ type = "docker"; service = "elasticsearch"; ready = $false }
    gateway       = @{ type = "http"; service = "gateway"; url = (Get-LocalServiceUrl -Name GATEWAY -DefaultPort 8080 -Path "/health"); ready = $false }
    # SeaweedFS storage publishes no host port; its container healthcheck
    # probes the internal S3 API.
    minio         = @{ type = "docker"; service = "minio"; ready = $false }
    temporal      = @{ type = "docker"; service = "temporal"; ready = $false }
    grafana       = @{ type = "http"; service = "grafana"; url = (Get-LocalServiceUrl -Name GRAFANA -DefaultPort 3000 -Path "/api/health"); ready = $false }
    notifications = @{ type = "docker"; service = "notifications-worker"; ready = $false }
    prometheus    = @{ type = "http"; service = "prometheus"; url = (Get-LocalServiceUrl -Name PROMETHEUS -DefaultPort 9090 -Path "/-/healthy"); ready = $false }
    # Probe a rendered route, not only the lightweight process health endpoint.
    # The first SSR render after an image update can take several seconds while
    # Node warms module caches, so give it a bounded one-time warmup window.
    frontend      = @{ type = "http"; service = "frontend"; url = (Get-LocalServiceUrl -Name FRONTEND -DefaultPort 8081 -Path "/login"); timeout = 20; ready = $false }
    imgproxy      = @{ type = "docker"; service = "imgproxy"; ready = $false }
    nats          = @{ type = "docker"; service = "nats"; ready = $false }
    outbox        = @{ type = "docker"; service = "outbox-worker"; ready = $false }
    spicedb       = @{ type = "docker"; service = "spicedb"; ready = $false }
    wshub         = @{ type = "http"; service = "ws-hub"; url = (Get-LocalServiceUrl -Name WS_HUB -DefaultPort 8083 -Path "/health"); ready = $false }
    caddy         = @{ type = "http"; service = "caddy"; url = (Get-LocalServiceUrl -Name CADDY_HTTP -DefaultPort 80 -Path "/healthz"); ready = $false }
    site          = @{ type = "http"; service = "caddy"; url = (Get-LocalServiceUrl -Name CADDY_HTTP -DefaultPort 80 -Path "/login"); timeout = 20; ready = $false }
    fileprocessor = @{ type = "docker"; service = "file-processor"; ready = $false }
    loki          = @{ type = "docker"; service = "loki-healthprobe"; ready = $false }
    tempo         = @{ type = "docker"; service = "tempo-healthprobe"; ready = $false }
    alloy         = @{ type = "docker"; service = "alloy"; ready = $false }
    pyroscope     = @{ type = "http"; service = "pyroscope"; url = (Get-LocalServiceUrl -Name PYROSCOPE -DefaultPort 4040 -Path "/ready"); ready = $false }
}

if ($script:LiveAcceptanceCore) {
    $services = Get-StartupReadinessInventory `
        -LiveAcceptanceCore `
        -CoreReadiness $coreReadiness `
        -FullReadiness $fullReadiness
} else {
    $services = Get-StartupReadinessInventory `
        -Core:$Core `
        -FullReadiness $fullReadiness
}

if ($Core) {
    Write-Status "Core mode readiness excludes search, Temporal, and observability probes."
}

do {
    Start-Sleep -Seconds 5
    $elapsed += 5

    foreach ($name in $services.Keys) {
        if ($services[$name].ready) { continue }

        if ($services[$name].type -in @("docker", "job")) {
            $serviceName = $services[$name].service
            if ($services[$name].type -eq "job") {
                $infoStr = & { $ErrorActionPreference = "SilentlyContinue"; docker compose @ComposeArgs --env-file $EnvFile ps --all $serviceName --format json 2>$null } | Out-String
            } else {
                $infoStr = & { $ErrorActionPreference = "SilentlyContinue"; docker compose @ComposeArgs --env-file $EnvFile ps $serviceName --format json 2>$null } | Out-String
            }
            $info = if ($infoStr -match "\{") { $infoStr | ConvertFrom-Json } else { $null }
            $rows = @($info)
            if ($services[$name].type -eq "job") {
                if ($rows.Count -eq 1 -and
                    [string]$rows[0].State -ieq "exited" -and
                    $null -ne $rows[0].PSObject.Properties["ExitCode"] -and
                    [long]$rows[0].ExitCode -eq 0) {
                    $services[$name].ready = $true
                }
            } elseif ($rows.Count -gt 0) {
                $allContainersReady = $true
                foreach ($row in $rows) {
                    $health = [string]$row.Health
                    $state = [string]$row.State
                    if ($health -cne "healthy" -and
                        -not ([string]::IsNullOrEmpty($health) -and $state -ceq "running")) {
                        $allContainersReady = $false
                    }
                }
                if ($allContainersReady) { $services[$name].ready = $true }
            }
        } else {
            $requestTimeout = if ($services[$name].ContainsKey("timeout")) {
                $services[$name].timeout
            } else {
                2
            }
            if (Test-ServiceHttp -Url $services[$name].url -Timeout $requestTimeout) {
                $services[$name].ready = $true
            }
        }
    }

    # Status line
    $statParts = @()
    foreach ($name in $services.Keys) {
        $icon = if ($services[$name].ready) { "+" } else { "." }
        $color = if ($services[$name].ready) { "Green" } else { "DarkGray" }
        $statParts += @{ name = $name; icon = $icon; color = $color }
    }
    Write-Host -NoNewline "  "
    foreach ($p in $statParts) {
        Write-Host -NoNewline "[$($p.icon)] $($p.name)  " -ForegroundColor $p.color
    }
    Write-Host ""  # newline

    $allReady = ($services.Values | Where-Object { -not $_.ready }).Count -eq 0

} while (-not $allReady -and $elapsed -lt $timeout)

if (-not $allReady) {
    Write-Err "Timeout after ${timeout}s. Failing services:"
    foreach ($name in $services.Keys) {
        if (-not $services[$name].ready) {
            $serviceName = $services[$name].service
            Write-Err "  $name ($serviceName) - showing last 15 log lines:"
            docker compose @ComposeArgs --env-file $EnvFile logs --tail=15 $serviceName 2>$null
            Write-Host ""
        }
    }
    exit 1
}

if (-not $Core -and -not $script:LiveAcceptanceCore) {
    Write-Status "Validating Prometheus scrape targets..."
    if (-not (Wait-PrometheusTargets)) {
        Write-Err "Prometheus has missing or unhealthy scrape targets."
        exit 1
    }
    Write-Ok "Prometheus scrape targets are healthy"
} elseif ($script:LiveAcceptanceCore) {
    Write-Status "Skipping Prometheus target validation; Prometheus is outside the signed live Core closure."
} else {
    Write-Status "Skipping Prometheus target validation in core mode (Prometheus is not started)."
}

# -- Done ---------------------------------------------------------------------

Write-Host ""
Write-Ok "University Ecosystem is running!"
if ($script:LiveAcceptanceCore) {
    Write-Host "  Mode: LIVE ACCEPTANCE CORE (23 signed services; full-stack acceptance is not implied)" -ForegroundColor Yellow
} elseif ($Core) {
    Write-Host "  Mode: CORE (search, Temporal, and observability containers are stopped; volumes are preserved)" -ForegroundColor Yellow
}
Write-Host ""
if ($script:LiveAcceptanceCore) {
    $siteUrl = Get-LocalServiceUrl -Name CADDY_HTTP -DefaultPort 80 -Path "/"
    $frontendUrl = Get-LocalServiceUrl -Name FRONTEND -DefaultPort 8081 -Path ""
    $gatewayUrl = Get-LocalServiceUrl -Name GATEWAY -DefaultPort 8080 -Path ""
    $backendUrl = Get-LocalServiceUrl -Name BACKEND -DefaultPort 8000 -Path ""
    $backendDocsUrl = Get-LocalServiceUrl -Name BACKEND -DefaultPort 8000 -Path "/docs"
    $wsHubUrl = Get-LocalServiceUrl -Name WS_HUB -DefaultPort 8083 -Path ""
    $mailpitUrl = Get-LocalServiceUrl -Name MAILPIT -DefaultPort 8025 -Path ""
    Write-Host "  >> Site (use this):  $siteUrl" -ForegroundColor Green
    Write-Host "  Live acceptance Core exposes only its signed app and Mailpit ports:" -ForegroundColor DarkGray
    Write-Host "  Frontend (Node SSR):  $frontendUrl  (no /api proxy - use $siteUrl)" -ForegroundColor DarkYellow
    Write-Host "  Gateway API:          $gatewayUrl" -ForegroundColor DarkYellow
    Write-Host "  Backend API:          $backendUrl  (127.0.0.1 only)" -ForegroundColor DarkYellow
    Write-Host "  API Docs:             $backendDocsUrl" -ForegroundColor DarkYellow
    Write-Host "  WS Hub:               $wsHubUrl" -ForegroundColor DarkYellow
    Write-Host "  Mailpit:              $mailpitUrl" -ForegroundColor DarkYellow
} else {
    $siteUrl = Get-LocalServiceUrl -Name CADDY_HTTP -DefaultPort 80 -Path "/"
    $frontendUrl = Get-LocalServiceUrl -Name FRONTEND -DefaultPort 8081 -Path ""
    $gatewayUrl = Get-LocalServiceUrl -Name GATEWAY -DefaultPort 8080 -Path ""
    $backendUrl = Get-LocalServiceUrl -Name BACKEND -DefaultPort 8000 -Path ""
    $backendDocsUrl = Get-LocalServiceUrl -Name BACKEND -DefaultPort 8000 -Path "/docs"
    $wsHubUrl = Get-LocalServiceUrl -Name WS_HUB -DefaultPort 8083 -Path ""
    $grafanaUrl = Get-LocalServiceUrl -Name GRAFANA -DefaultPort 3000 -Path ""
    $prometheusUrl = Get-LocalServiceUrl -Name PROMETHEUS -DefaultPort 9090 -Path ""
    $pyroscopeUrl = Get-LocalServiceUrl -Name PYROSCOPE -DefaultPort 4040 -Path ""
    $alloyUrl = Get-LocalServiceUrl -Name ALLOY -DefaultPort 12345 -Path ""
    Write-Host "  >> Site (use this):  $siteUrl" -ForegroundColor Green
    Write-Host "     Caddy reverse proxy routes /api/* -> gateway:8080 -> backend:8000," -ForegroundColor DarkGray
    Write-Host "     /ws/* -> ws-hub:8081, /sw.js -> frontend:3000, default -> frontend:3000." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Direct service ports (admin/debug only - browser API calls won't work)" -ForegroundColor Gray
    Write-Host "  Frontend (Node SSR):  $frontendUrl  (no /api proxy - use $siteUrl)" -ForegroundColor DarkYellow
    Write-Host "  Gateway API:          $gatewayUrl" -ForegroundColor DarkYellow
    Write-Host "  Backend API:          $backendUrl  (127.0.0.1 only)" -ForegroundColor DarkYellow
    Write-Host "  API Docs:             $backendDocsUrl" -ForegroundColor DarkYellow
    Write-Host "  WS Hub:               $wsHubUrl" -ForegroundColor DarkYellow
    Write-Host "  SeaweedFS S3 API:     minio:9000 (internal Compose network only)" -ForegroundColor DarkYellow
    Write-Host "  Grafana:              $grafanaUrl" -ForegroundColor DarkYellow
    Write-Host "  Prometheus:           $prometheusUrl" -ForegroundColor DarkYellow
    Write-Host "  Pyroscope:            $pyroscopeUrl" -ForegroundColor DarkYellow
    Write-Host "  Alloy:                $alloyUrl" -ForegroundColor DarkYellow
}
Write-Host ""
Write-Host "Demo seeding and optional live E2E stand (separate from this stack):" -ForegroundColor Cyan
Write-Host "  Use the owner-checked stand for synthetic demo data; direct seeding into this Compose database is disabled."
Write-Host "  The stand runs the full stack by default; explicitly select its owner-bound Core dependency closure with --stack core."
Write-Host "  Choose a stack only when host resources are available for that selection."
Write-Host "       python scripts/live_stand.py up --ref HEAD"
Write-Host "       python scripts/live_stand.py seed --demo"
Write-Host "       python scripts/live_stand.py e2e (optional)"
Write-Host ""
Write-Host "Commands:" -ForegroundColor Gray
Write-Host "  Stop:      .\start-docker.ps1 -Down"
Write-Host "  Logs:      .\start-docker.ps1 -Logs"
Write-Host "  Logs svc:  .\start-docker.ps1 -Logs -LogService backend"
Write-Host "  Build:     .\start-docker.ps1 -Build"
Write-Host "  Rebuild:   .\start-docker.ps1 -Rebuild   (no cache)"
Write-Host "  Core:      .\start-docker.ps1 -Core     (resource-conscious app stack)"
Write-Host "  Lean:      .\start-docker.ps1 -Lean     (alias for -Core)"
