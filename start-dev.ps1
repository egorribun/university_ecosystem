$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$api  = Join-Path $root "root"
$web  = Join-Path $api "frontend"

Set-Location $api
if (!(Test-Path ".venv")) { py -3 -m venv .venv }

$python = Join-Path $api ".venv\Scripts\python.exe"

& $python -m pip install -U pip wheel
if (Test-Path "requirements-dev.txt") {
  & $python -m pip install -r requirements-dev.txt
} else {
  & $python -m pip install -r requirements.txt
}

$env:APP_ENV = "development"
$env:DATABASE_URL = "sqlite+aiosqlite:///./dev.db"
$env:AUTO_CREATE_SCHEMA = "1"
$env:FRONTEND_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"

if (!(Test-Path ".env")) {
@"
APP_ENV=$($env:APP_ENV)
DATABASE_URL=$($env:DATABASE_URL)
AUTO_CREATE_SCHEMA=$($env:AUTO_CREATE_SCHEMA)
FRONTEND_ORIGINS=$($env:FRONTEND_ORIGINS)
"@ | Out-File -Encoding ascii ".env"
}

Start-Process -FilePath "cmd.exe" -ArgumentList "/k",".venv\Scripts\python -m uvicorn app.main:app --reload --lifespan=off" -WorkingDirectory $api

if (Test-Path $web) {
  Start-Process -FilePath "cmd.exe" -ArgumentList "/k","npm install && npm run dev" -WorkingDirectory $web
  Start-Process "http://localhost:5173"
}