param(
  [switch]$LocalDb = $false,
  [switch]$NoBuild = $false
)

$ErrorActionPreference = "Stop"

# Fix emoji / UTF-8
chcp 65001 | Out-Null
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()

# Enable BuildKit
if (-not $env:DOCKER_BUILDKIT) { $env:DOCKER_BUILDKIT = "1" }

$composeFile = "infra/compose/docker-compose.yml"
$profileArg  = $LocalDb.IsPresent ? "--profile local-db" : ""

Write-Host "🚀 Starting MozaiksAI..." -ForegroundColor Green

if (-not $NoBuild) {
  Write-Host "Building app image..." -ForegroundColor Yellow
  docker build -f infra/docker/Dockerfile -t mozaiksai-app:latest .
  if ($LASTEXITCODE -ne 0) { Write-Host "❌ Failed to build image" -ForegroundColor Red; exit 1 }
  Write-Host "✅ Image built successfully" -ForegroundColor Green
} else {
  Write-Host "⏭️  Skipping build (NoBuild)" -ForegroundColor Yellow
}

Write-Host "Starting services..." -ForegroundColor Yellow
docker compose -f $composeFile up -d $profileArg
if ($LASTEXITCODE -ne 0) {
  Write-Host "❌ Failed to start services" -ForegroundColor Red
  docker compose -f $composeFile logs --no-color --tail=200
  exit 1
}

Write-Host "✅ Services started successfully!" -ForegroundColor Green
Write-Host "🌐 App available at: http://localhost:8000" -ForegroundColor Cyan

# Figure out Mongo target without leaking creds
function Get-HostFromUri([string]$uri) {
  if ([string]::IsNullOrWhiteSpace($uri)) { return "<unknown>" }
  try {
    $tmp = $uri -replace '^mongodb\+srv://','mongodb://'
    $u = [Uri]$tmp
    return $u.Host
  } catch {
    # fallback: parse after '@' if present
    if ($uri -match '@([^/?]+)') { return $Matches[1] }
    return "<parse-failed>"
  }
}

# Prefer MONGO_URI if set on host; otherwise describe the source
$mongoUriEnv = $env:MONGO_URI
if ($LocalDb) {
  $mongoHint = "mongodb://mongo:27017 (local profile)"
} elseif ($mongoUriEnv) {
  $mongoHint = $mongoUriEnv
} else {
  $mongoHint = "<KeyVault:MongoURI> (resolved inside container)"
}

$mongoHost = Get-HostFromUri $mongoHint
$usesSrv = ($mongoHint -like "mongodb+srv://*")
Write-Host ("📊 Mongo target host: {0} (srv={1})" -f $mongoHost, $usesSrv) -ForegroundColor Cyan

Write-Host "`n📋 Service Status:" -ForegroundColor Yellow
docker compose -f $composeFile ps
