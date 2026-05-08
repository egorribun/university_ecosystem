<#
.SYNOPSIS
    Start the University Ecosystem site using Docker Compose.

.DESCRIPTION
    Builds and starts all Docker containers for the full site.
    Generates secure secrets if .env / .env.docker don't exist.
    Creates MinIO bucket and SpiceDB database on first run.

.EXAMPLE
    .\start-docker.ps1            # Start (no rebuild)
    .\start-docker.ps1 -Build     # Build (cached) then start
    .\start-docker.ps1 -Rebuild   # Build (no-cache) then start
    .\start-docker.ps1 -Down      # Stop all containers
    .\start-docker.ps1 -Logs                  # Follow all logs
    .\start-docker.ps1 -Logs -LogService backend  # Follow one service
#>

param(
    [switch]$Build,
    [switch]$Rebuild,
    [switch]$Down,
    [switch]$Logs,
    [string]$LogService = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$ComposeFile = "docker-compose.full.yml"
$EnvFile = ".env.docker"
$EnvCompose = ".env"

# ── Helpers ──────────────────────────────────────────────────────────────────

function Write-Status  { param([string]$Msg) Write-Host "[*] $Msg" -ForegroundColor Cyan }
function Write-Ok      { param([string]$Msg) Write-Host "[+] $Msg" -ForegroundColor Green }
function Write-Err     { param([string]$Msg) Write-Host "[-] $Msg" -ForegroundColor Red }
function Write-Warn    { param([string]$Msg) Write-Host "[!] $Msg" -ForegroundColor Yellow }

function New-Secret {
    param([int]$Length = 32)
    $chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    -join ((1..$Length) | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
}

function New-HexSecret {
    param([int]$Length = 32)
    -join ((1..$Length) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) })
}

function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    [System.IO.File]::WriteAllText(
        (Join-Path $ProjectRoot $Path),
        $Content,
        [System.Text.UTF8Encoding]::new($false)
    )
}

# Wave 137 SW1: Generate RSA-2048 keypair for backend JWT RS256 signing.
# Idempotent — skips generation if key file already exists.
# Uses .NET 8 native PEM export (PowerShell 7+ ships .NET 8 with
# RSA.ExportPkcs8PrivateKeyPem). Falls back to OpenSSL if available.
# Closes W135 §Honesty #9 SSR auth-at-edge layer (jose.createRemoteJWKSet
# requires RS256; pre-W137 dev backend signed HS256).
function New-JwtRs256Key {
    param([string]$OutputPath = ".secrets/jwt_rs256.pem")

    $absoluteOutputPath = Join-Path $ProjectRoot $OutputPath
    if (Test-Path $absoluteOutputPath) {
        Write-Ok "RSA-2048 keypair already exists at $OutputPath (idempotent skip)"
        return
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
        Write-Warn ".NET 8 RSA.ExportPkcs8PrivateKeyPem unavailable; falling back to openssl"
        # Path B: openssl fallback (requires openssl in PATH)
        $tempKey = [System.IO.Path]::GetTempFileName()
        try {
            $null = openssl genrsa -out $tempKey 2048 2>&1
            if ($LASTEXITCODE -ne 0) {
                Remove-Item $tempKey -ErrorAction SilentlyContinue
                throw "openssl genrsa failed (exit $LASTEXITCODE). Install OpenSSL or upgrade to PowerShell 7.4+ (.NET 8)."
            }
            $pem = Get-Content $tempKey -Raw
        } finally {
            Remove-Item $tempKey -ErrorAction SilentlyContinue
        }
    }

    if (-not $pem) {
        throw "Failed to generate RSA private key — neither .NET nor openssl path succeeded."
    }

    [System.IO.File]::WriteAllText(
        $absoluteOutputPath,
        $pem,
        [System.Text.UTF8Encoding]::new($false)
    )

    Write-Ok "Generated RSA-2048 keypair at $OutputPath"
}

function Test-ServiceHttp {
    param([string]$Url, [int]$Timeout = 2)
    try { (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $Timeout).StatusCode -eq 200 }
    catch { $false }
}

# ── Prerequisite: Docker running ─────────────────────────────────────────────

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

# ── Handle -Down ─────────────────────────────────────────────────────────────

if ($Down) {
    Write-Status "Stopping all containers..."
    $envArgs = if (Test-Path $EnvFile) { @("--env-file", $EnvFile) } else { @() }
    docker compose -f $ComposeFile @envArgs down
    Write-Ok "All containers stopped"
    exit 0
}

# ── Handle -Logs ─────────────────────────────────────────────────────────────

if ($Logs) {
    $envArgs = if (Test-Path $EnvFile) { @("--env-file", $EnvFile) } else { @() }
    if ($LogService) {
        docker compose -f $ComposeFile @envArgs logs -f $LogService
    } else {
        docker compose -f $ComposeFile @envArgs logs -f
    }
    exit 0
}

# ── Generate secrets ─────────────────────────────────────────────────────────

$generated = $false

$needsEnvDocker = -not (Test-Path $EnvFile)
$needsEnvCompose = -not (Test-Path $EnvCompose)

if ($needsEnvDocker -and $needsEnvCompose) {
    # Both missing — fresh setup, generate from scratch
    Write-Status "Generating environment files with secure secrets..."

    $postgresPassword = New-Secret -Length 32
    $secretKey         = New-Secret -Length 64
    $minioPassword     = New-Secret -Length 24
    $redisPassword     = New-Secret -Length 24
    $elasticPassword   = New-Secret -Length 24
    $natsPassword      = New-Secret -Length 24
    $spicedbKey        = New-Secret -Length 32
    $wsHubSecret       = New-Secret -Length 32
    $grafanaPassword   = New-Secret -Length 24

    # ── .env.docker (container env_file) ─────────────────────────────────
    $dockerEnv = @"
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$postgresPassword
POSTGRES_DB=university
SECRET_KEY=$secretKey
ALGORITHM=RS256
JWT_PRIVATE_KEY_PATH=.secrets/jwt_rs256.pem
ACCESS_TOKEN_EXPIRE_MINUTES=30
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=$minioPassword
ELASTIC_PASSWORD=$elasticPassword
NATS_USER=app
NATS_PASSWORD=$natsPassword
SPICEDB_PRESHARED_KEY=$spicedbKey
WS_HUB_INTERNAL_SECRET=$wsHubSecret
GRAFANA_ADMIN_PASSWORD=$grafanaPassword
REDIS_PASSWORD=$redisPassword
VAPID_SUBJECT=mailto:admin@example.com
ENVIRONMENT=development
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=
SPOTIFY_SCOPES=
"@
    Write-Utf8NoBom $EnvFile $dockerEnv

    # ── .env (compose interpolation) ─────────────────────────────────────
    $composeEnv = @"
# Auto-generated by start-docker.ps1 — used for docker compose interpolation.
# Passwords MUST match .env.docker. Re-run start-docker.ps1 after editing.
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$postgresPassword
POSTGRES_DB=university
SECRET_KEY=$secretKey
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=$minioPassword
ELASTIC_PASSWORD=$elasticPassword
NATS_USER=app
NATS_PASSWORD=$natsPassword
SPICEDB_PRESHARED_KEY=$spicedbKey
WS_HUB_INTERNAL_SECRET=$wsHubSecret
GRAFANA_ADMIN_PASSWORD=$grafanaPassword
REDIS_PASSWORD=$redisPassword
ENVIRONMENT=development
VAPID_SUBJECT=mailto:admin@example.com
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=
SPOTIFY_SCOPES=
"@
    Write-Utf8NoBom $EnvCompose $composeEnv

    Write-Ok "Generated $EnvFile and $EnvCompose with secure secrets"
    $generated = $true
} elseif ($needsEnvDocker -and -not $needsEnvCompose) {
    # .env exists but .env.docker missing — copy .env as base for .env.docker
    Write-Warn ".env.docker missing — deriving from .env..."
    Copy-Item $EnvCompose $EnvFile
    Write-Ok "Created $EnvFile from $EnvCompose"
    $generated = $true
} elseif (-not $needsEnvDocker -and $needsEnvCompose) {
    # .env.docker exists but .env missing — derive .env from .env.docker
    Write-Warn ".env missing — deriving from .env.docker..."
    Copy-Item $EnvFile $EnvCompose
    Write-Ok "Created $EnvCompose from $EnvFile"
    $generated = $true
}

# ── Sync check: ensure .env has all required vars ────────────────────────────

if (-not $generated) {
    $envContent = Get-Content $EnvCompose -Raw -ErrorAction SilentlyContinue
    $missing = @()
    foreach ($key in @("WS_HUB_INTERNAL_SECRET", "REDIS_PASSWORD", "MINIO_ROOT_PASSWORD", "SPICEDB_PRESHARED_KEY", "GRAFANA_ADMIN_PASSWORD")) {
        if ($envContent -notmatch "(?m)^$key=") {
            $missing += $key
        }
    }
    if ($missing.Count -gt 0) {
        Write-Warn "Missing vars in .env: $($missing -join ', '). Reading from .env.docker..."
        $dockerLines = Get-Content $EnvFile -ErrorAction SilentlyContinue
        $patch = ""
        foreach ($key in $missing) {
            $line = $dockerLines | Where-Object { $_ -match "^$key=" } | Select-Object -First 1
            if ($line) { $patch += "`n$line" }
        }
        if ($patch) {
            Add-Content -Path $EnvCompose -Value $patch -NoNewline:$false
            Write-Ok "Patched .env with missing vars"
        }
    }
}

# ── Wave 137 SW1: Migrate existing .env.docker to RS256 ──────────────────────
# Pre-W137 .env.docker has ALGORITHM=HS256 (no JWT_PRIVATE_KEY_PATH).
# Post-W137 expects ALGORITHM=RS256 + JWT_PRIVATE_KEY_PATH=.secrets/jwt_rs256.pem.
# Auto-patch existing files for seamless upgrade.
if (Test-Path $EnvFile) {
    $envDockerContent = Get-Content $EnvFile -Raw -ErrorAction SilentlyContinue
    $needsAlgorithmFlip = $envDockerContent -match "(?m)^ALGORITHM=HS256\s*$"
    $needsKeyPath = $envDockerContent -notmatch "(?m)^JWT_PRIVATE_KEY_PATH="

    if ($needsAlgorithmFlip -or $needsKeyPath) {
        Write-Status "Migrating $EnvFile to RS256 (Wave 137 SW1)..."

        if ($needsAlgorithmFlip) {
            $envDockerContent = $envDockerContent -replace "(?m)^ALGORITHM=HS256\s*$", "ALGORITHM=RS256"
            Write-Ok "Flipped ALGORITHM=HS256 → ALGORITHM=RS256"
        }

        if ($needsKeyPath) {
            # Insert JWT_PRIVATE_KEY_PATH after ALGORITHM line (or after SECRET_KEY if ALGORITHM missing)
            if ($envDockerContent -match "(?m)^ALGORITHM=") {
                $envDockerContent = $envDockerContent -replace `
                    "((?m)^ALGORITHM=[^\r\n]*)", `
                    "`$1`nJWT_PRIVATE_KEY_PATH=.secrets/jwt_rs256.pem"
            } else {
                $envDockerContent += "`nJWT_PRIVATE_KEY_PATH=.secrets/jwt_rs256.pem"
            }
            Write-Ok "Added JWT_PRIVATE_KEY_PATH=.secrets/jwt_rs256.pem"
        }

        Write-Utf8NoBom $EnvFile $envDockerContent.TrimEnd()
    }
}

# ── Wave 137 SW1: Generate RSA-2048 keypair for JWT RS256 signing ─────────────
# Backend reads .secrets/jwt_rs256.pem at startup (jwt_settings.py:202-205).
# Volume-mounted into container at /app/.secrets/jwt_rs256.pem.
New-JwtRs256Key -OutputPath ".secrets/jwt_rs256.pem"

# ── Build ────────────────────────────────────────────────────────────────────

if ($Rebuild) {
    Write-Status "Rebuilding ALL images (no cache)..."
    docker compose -f $ComposeFile --env-file $EnvFile build --no-cache
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Build failed. Check output above."
        exit 1
    }
    Write-Ok "All images rebuilt"
} elseif ($Build) {
    Write-Status "Building images (cached)..."
    docker compose -f $ComposeFile --env-file $EnvFile build
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Build failed. Check output above."
        exit 1
    }
    Write-Ok "Images built"
}

# ── Start services ───────────────────────────────────────────────────────────

Write-Status "Starting containers..."
docker compose -f $ComposeFile --env-file $EnvFile up -d
if ($LASTEXITCODE -ne 0) {
    Write-Err "Failed to start containers."
    exit 1
}

# ── First-run initialization ─────────────────────────────────────────────────

# SpiceDB needs its own database in Postgres (idempotent)
Write-Status "Ensuring SpiceDB database exists..."
docker compose -f $ComposeFile --env-file $EnvFile exec -T postgres psql -U postgres -c "CREATE DATABASE spicedb" 2>$null
# Ignore errors — database may already exist

# SpiceDB needs migrations after fresh DB creation
Write-Status "Running SpiceDB migrations..."
$pgPass = (Select-String -Path $EnvFile -Pattern "^POSTGRES_PASSWORD=(.+)$").Matches.Groups[1].Value
$projectName = (Split-Path $ProjectRoot -Leaf).ToLower() -replace '[^a-z0-9]', '_'
$network = "${projectName}_internal"
docker run --rm --network $network authzed/spicedb:v1.51.0 migrate head --datastore-engine postgres --datastore-conn-uri "postgres://postgres:${pgPass}@postgres:5432/spicedb?sslmode=disable" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Ok "SpiceDB migrations applied"
} else {
    Write-Warn "SpiceDB migration failed or already up-to-date"
}

# MinIO bucket (wait for MinIO to be healthy, then create via minio/mc container)
Write-Status "Ensuring MinIO 'uploads' bucket exists..."
$minioReady = $false
for ($i = 0; $i -lt 12; $i++) {
    $health = docker compose -f $ComposeFile --env-file $EnvFile ps minio --format json 2>$null | ConvertFrom-Json
    $h = if ($health -is [array]) { $health[0].Health } else { $health.Health }
    if ($h -eq "healthy") { $minioReady = $true; break }
    Start-Sleep -Seconds 5
}
if ($minioReady) {
    $minioPass = (Select-String -Path $EnvFile -Pattern "^MINIO_ROOT_PASSWORD=(.+)$").Matches.Groups[1].Value
    # mc is NOT in minio/minio image — use separate minio/mc container on the same network
    $projectName = (Split-Path $ProjectRoot -Leaf).ToLower() -replace '[^a-z0-9]', '_'
    $network = "${projectName}_internal"
    docker run --rm --network $network --entrypoint "" minio/mc sh -c "mc alias set local http://minio:9000 minioadmin $minioPass && mc mb local/uploads --ignore-existing" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "MinIO bucket ready"
    } else {
        Write-Warn "Could not create MinIO bucket — create manually after startup"
    }
} else {
    Write-Warn "MinIO not healthy yet — create bucket manually after startup"
}

# ── Health check loop ────────────────────────────────────────────────────────

Write-Status "Waiting for services..."
$timeout = 120
$elapsed = 0
$services = @{
    postgres = @{ type = "docker"; ready = $false }
    backend  = @{ type = "docker"; ready = $false }
    nats     = @{ type = "docker"; ready = $false }
    gateway  = @{ type = "http"; url = "http://localhost:8080/health"; ready = $false }
    wshub    = @{ type = "http"; url = "http://localhost:8083/health"; ready = $false }
    frontend = @{ type = "http"; url = "http://localhost:8081"; ready = $false }
}

do {
    Start-Sleep -Seconds 5
    $elapsed += 5

    foreach ($name in $services.Keys) {
        if ($services[$name].ready) { continue }

        if ($services[$name].type -eq "docker") {
            $info = docker compose -f $ComposeFile --env-file $EnvFile ps $name --format json 2>$null | ConvertFrom-Json
            $h = if ($info -is [array]) { $info[0].Health } else { $info.Health }
            if ($h -eq "healthy") { $services[$name].ready = $true }
        } else {
            if (Test-ServiceHttp $services[$name].url) { $services[$name].ready = $true }
        }
    }

    # Status line
    $statParts = @()
    foreach ($name in @("postgres", "backend", "gateway", "frontend", "nats", "wshub")) {
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
            Write-Err "  $name — showing last 15 log lines:"
            docker compose -f $ComposeFile --env-file $EnvFile logs --tail=15 $name 2>$null
            Write-Host ""
        }
    }
    exit 1
}

# ── Done ─────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Ok "University Ecosystem is running!"
Write-Host ""
Write-Host "  Frontend:    http://localhost:8081" -ForegroundColor Yellow
Write-Host "  Gateway API: http://localhost:8080" -ForegroundColor Yellow
Write-Host "  Backend API: http://localhost:8000" -ForegroundColor Yellow
Write-Host "  API Docs:    http://localhost:8000/docs" -ForegroundColor Yellow
Write-Host "  WS Hub:      http://localhost:8083" -ForegroundColor Yellow
Write-Host "  MinIO:       http://localhost:9001" -ForegroundColor Yellow
Write-Host "  Grafana:     http://localhost:3000" -ForegroundColor Yellow
Write-Host ""
Write-Host "Commands:" -ForegroundColor Gray
Write-Host "  Stop:      .\start-docker.ps1 -Down"
Write-Host "  Logs:      .\start-docker.ps1 -Logs"
Write-Host "  Logs svc:  .\start-docker.ps1 -Logs -LogService backend"
Write-Host "  Build:     .\start-docker.ps1 -Build"
Write-Host "  Rebuild:   .\start-docker.ps1 -Rebuild   (no cache)"
