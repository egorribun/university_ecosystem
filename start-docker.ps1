<#
.SYNOPSIS
    Start the University Ecosystem site using Docker Compose.

.DESCRIPTION
    Builds and starts all Docker containers for the full site.
    Generates secure secrets if .env.docker doesn't exist.

.EXAMPLE
    .\start-docker.ps1
    .\start-docker.ps1 -Build
    .\start-docker.ps1 -Down
#>

param(
    [switch]$Build,
    [switch]$Down,
    [switch]$Logs
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$ComposeFile = "docker-compose.full.yml"
$EnvFile = ".env.docker"

function Write-Status {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[+] $Message" -ForegroundColor Green
}

function Write-Error {
    param([string]$Message)
    Write-Host "[-] $Message" -ForegroundColor Red
}

function New-SecureString {
    param([int]$Length = 32)
    $chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    -join ((1..$Length) | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
}

# Generate .env.docker if missing
if (-not (Test-Path $EnvFile)) {
    Write-Status "Generating $EnvFile with secure secrets..."

    $postgresPassword = New-SecureString -Length 32
    $secretKey = New-SecureString -Length 64
    $minioPassword = New-SecureString -Length 24
    $elasticPassword = New-SecureString -Length 24
    $natsPassword = New-SecureString -Length 24
    $garageRpcSecret = -join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) })
    $garageAdminToken = New-SecureString -Length 32
    $spicedbKey = New-SecureString -Length 32
    $wsHubSecret = New-SecureString -Length 32
    $grafanaPassword = New-SecureString -Length 24

    $envContent = @"
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$postgresPassword
POSTGRES_DB=university
SECRET_KEY=$secretKey
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=$minioPassword
ELASTIC_PASSWORD=$elasticPassword
NATS_USER=app
NATS_PASSWORD=$natsPassword
GARAGE_RPC_SECRET=$garageRpcSecret
GARAGE_ADMIN_TOKEN=$garageAdminToken
SPICEDB_PRESHARED_KEY=$spicedbKey
WS_HUB_INTERNAL_SECRET=$wsHubSecret
GRAFANA_ADMIN_PASSWORD=$grafanaPassword
REDIS_PASSWORD=$minioPassword
VAPID_SUBJECT=mailto:admin@example.com
ENVIRONMENT=development
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=
SPOTIFY_SCOPES=
"@
    # Write without BOM — docker compose cannot parse UTF-8 BOM
    [System.IO.File]::WriteAllText((Join-Path $ProjectRoot $EnvFile), $envContent, [System.Text.UTF8Encoding]::new($false))

    Write-Success "Generated $EnvFile with secure secrets"
}

# Handle -Down flag
if ($Down) {
    Write-Status "Stopping all containers..."
    docker compose -f $ComposeFile --env-file $EnvFile down
    Write-Success "All containers stopped"
    exit 0
}

# Handle -Logs flag
if ($Logs) {
    docker compose -f $ComposeFile --env-file $EnvFile logs -f
    exit 0
}

# Build images if requested or if they don't exist
if ($Build) {
    Write-Status "Building Docker images..."
    docker compose -f $ComposeFile --env-file $EnvFile build
}

# Start services
Write-Status "Starting Docker containers..."
docker compose -f $ComposeFile --env-file $EnvFile up -d

# Wait for services to be healthy
Write-Status "Waiting for services to become healthy..."
$timeout = 120
$elapsed = 0

do {
    Start-Sleep -Seconds 5
    $elapsed += 5

    $backendHealth = docker compose -f $ComposeFile ps backend --format json 2>$null | ConvertFrom-Json
    $postgresHealth = docker compose -f $ComposeFile ps postgres --format json 2>$null | ConvertFrom-Json
    $natsHealth = docker compose -f $ComposeFile ps nats --format json 2>$null | ConvertFrom-Json

    # Handle both single object and array output from docker compose ps
    $backendReady = if ($backendHealth -is [array]) { $backendHealth[0].Health -eq "healthy" } else { $backendHealth.Health -eq "healthy" }
    $postgresReady = if ($postgresHealth -is [array]) { $postgresHealth[0].Health -eq "healthy" } else { $postgresHealth.Health -eq "healthy" }
    $natsReady = if ($natsHealth -is [array]) { $natsHealth[0].Health -eq "healthy" } else { $natsHealth.Health -eq "healthy" }

    # Gateway and WS-Hub use distroless images (no shell) — probe via HTTP from host
    $gatewayReady = try { (Invoke-WebRequest -Uri http://localhost:8080/health -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { $false }
    $wsHubReady = try { (Invoke-WebRequest -Uri http://localhost:8083/health -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { $false }

    Write-Host "  Backend: $(if ($backendReady) { 'Ready' } else { 'Starting...' }) | Gateway: $(if ($gatewayReady) { 'Ready' } else { 'Starting...' }) | WS-Hub: $(if ($wsHubReady) { 'Ready' } else { 'Starting...' }) | NATS: $(if ($natsReady) { 'Ready' } else { 'Starting...' })"

} while ((-not $backendReady -or -not $postgresReady -or -not $natsReady -or -not $gatewayReady -or -not $wsHubReady) -and $elapsed -lt $timeout)

if ($elapsed -ge $timeout) {
    Write-Error "Timeout waiting for services. Check logs with: .\start-docker.ps1 -Logs"
    exit 1
}

Write-Host ""
Write-Success "University Ecosystem is running!"
Write-Host ""
Write-Host "  Frontend:    http://localhost:8081" -ForegroundColor Yellow
Write-Host "  Gateway API: http://localhost:8080" -ForegroundColor Yellow
Write-Host "  Backend API: http://localhost:8000" -ForegroundColor Yellow
Write-Host "  API Docs:    http://localhost:8000/docs" -ForegroundColor Yellow
Write-Host "  WS Hub:      http://localhost:8083" -ForegroundColor Yellow
Write-Host "  Grafana:     http://localhost:3000 (localhost only)" -ForegroundColor Yellow
Write-Host ""
Write-Host "Commands:" -ForegroundColor Gray
Write-Host "  Stop:   .\start-docker.ps1 -Down"
Write-Host "  Logs:   .\start-docker.ps1 -Logs"
Write-Host "  Rebuild: .\start-docker.ps1 -Build"
