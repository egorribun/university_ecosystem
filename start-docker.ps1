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

    @"
# Auto-generated Docker environment configuration
# Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

POSTGRES_USER=postgres
POSTGRES_PASSWORD=$postgresPassword
POSTGRES_DB=university

SECRET_KEY=$secretKey
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=$minioPassword

VAPID_SUBJECT=mailto:admin@example.com
ENVIRONMENT=development
"@ | Out-File -Encoding UTF8 $EnvFile

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
    $rustOptimizerHealth = docker compose -f $ComposeFile ps rust-optimizer --format json 2>$null | ConvertFrom-Json
    $natsHealth = docker compose -f $ComposeFile ps nats --format json 2>$null | ConvertFrom-Json
    $gatewayHealth = docker compose -f $ComposeFile ps gateway --format json 2>$null | ConvertFrom-Json
    $wsHubHealth = docker compose -f $ComposeFile ps ws-hub --format json 2>$null | ConvertFrom-Json

    # Handle both single object and array output from docker compose ps
    $backendReady = if ($backendHealth -is [array]) { $backendHealth[0].Health -eq "healthy" } else { $backendHealth.Health -eq "healthy" }
    $postgresReady = if ($postgresHealth -is [array]) { $postgresHealth[0].Health -eq "healthy" } else { $postgresHealth.Health -eq "healthy" }
    $rustOptimizerReady = if ($rustOptimizerHealth -is [array]) { $rustOptimizerHealth[0].Health -eq "healthy" } else { $rustOptimizerHealth.Health -eq "healthy" }
    $natsReady = if ($natsHealth -is [array]) { $natsHealth[0].Health -eq "healthy" } else { $natsHealth.Health -eq "healthy" }
    $gatewayReady = if ($gatewayHealth -is [array]) { $gatewayHealth[0].Health -eq "healthy" } else { $gatewayHealth.Health -eq "healthy" }
    $wsHubReady = if ($wsHubHealth -is [array]) { $wsHubHealth[0].Health -eq "healthy" } else { $wsHubHealth.Health -eq "healthy" }

    Write-Host "  Backend: $(if ($backendReady) { 'Ready' } else { 'Starting...' }) | Gateway: $(if ($gatewayReady) { 'Ready' } else { 'Starting...' }) | WS-Hub: $(if ($wsHubReady) { 'Ready' } else { 'Starting...' }) | Rust: $(if ($rustOptimizerReady) { 'Ready' } else { 'Starting...' })"

} while ((-not $backendReady -or -not $postgresReady -or -not $rustOptimizerReady -or -not $natsReady -or -not $gatewayReady -or -not $wsHubReady) -and $elapsed -lt $timeout)

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
Write-Host "  Grafana:     http://localhost:3000" -ForegroundColor Yellow
Write-Host "  MinIO:       http://localhost:9001" -ForegroundColor Yellow
Write-Host "  Rust Opt:    http://localhost:8090" -ForegroundColor Yellow
Write-Host "  NATS Mon:    http://localhost:8222" -ForegroundColor Yellow
Write-Host "  ES Search:   http://localhost:9200" -ForegroundColor Yellow
Write-Host ""
Write-Host "Commands:" -ForegroundColor Gray
Write-Host "  Stop:   .\start-docker.ps1 -Down"
Write-Host "  Logs:   .\start-docker.ps1 -Logs"
Write-Host "  Rebuild: .\start-docker.ps1 -Build"
