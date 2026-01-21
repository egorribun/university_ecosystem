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

    $backendReady = $backendHealth.Health -eq "healthy"
    $postgresReady = $postgresHealth.Health -eq "healthy"

    Write-Host "  Backend: $(if ($backendReady) { 'Ready' } else { 'Starting...' }) | Postgres: $(if ($postgresReady) { 'Ready' } else { 'Starting...' })"

} while ((-not $backendReady -or -not $postgresReady) -and $elapsed -lt $timeout)

if ($elapsed -ge $timeout) {
    Write-Error "Timeout waiting for services. Check logs with: .\start-docker.ps1 -Logs"
    exit 1
}

Write-Host ""
Write-Success "University Ecosystem is running!"
Write-Host ""
Write-Host "  Frontend:    http://localhost:8081" -ForegroundColor Yellow
Write-Host "  Backend API: http://localhost:8000" -ForegroundColor Yellow
Write-Host "  API Docs:    http://localhost:8000/docs" -ForegroundColor Yellow
Write-Host "  MinIO:       http://localhost:9001" -ForegroundColor Yellow
Write-Host ""
Write-Host "Commands:" -ForegroundColor Gray
Write-Host "  Stop:   .\start-docker.ps1 -Down"
Write-Host "  Logs:   .\start-docker.ps1 -Logs"
Write-Host "  Rebuild: .\start-docker.ps1 -Build"
