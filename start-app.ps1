param(
  [switch]$NoBuild = $false
)

$ErrorActionPreference = "Stop"

# Ensure UTF-8 output (compatible with PowerShell 5.1)
chcp 65001 | Out-Null
$utf8 = [System.Text.Encoding]::UTF8
$OutputEncoding = [Console]::OutputEncoding = $utf8

# Enable BuildKit
if (-not $env:DOCKER_BUILDKIT) { $env:DOCKER_BUILDKIT = "1" }

$composeFile = "infra/compose/docker-compose.yml"

# Emoji/icons (constructed safely so the file avoids direct surrogate encoding issues)
$rocket = "$( [char]0xD83D )$( [char]0xDE80 )"   # 🚀
$cross = [char]0x274C                              # ❌
$check = [char]0x2705                              # ✅
$skip = [char]0x23ED                               # ⏭
$globe = "$( [char]0xD83C )$( [char]0xDF10 )"     # 🌐
$chart = "$( [char]0xD83D )$( [char]0xDCCA )"     # 📊
$clip = "$( [char]0xD83D )$( [char]0xDCCB )"      # 📋

# Azure credential validation (avoid literal emojis for PS 5.1 safety)
Write-Host "Checking Azure credentials..." -ForegroundColor Yellow
if ($env:AZURE_CLIENT_SECRET -and ($env:AZURE_CLIENT_SECRET -like 'https://*')) {
  Write-Host ("$cross AZURE_CLIENT_SECRET looks like a URL - use the secret VALUE") -ForegroundColor Red
  exit 1
}

if ($env:AZURE_CLIENT_ID -and $env:AZURE_TENANT_ID -and $env:AZURE_CLIENT_SECRET) {
  Write-Host ("$check Complete Azure credentials detected") -ForegroundColor Green
} elseif ($env:AZURE_CLIENT_ID -or $env:AZURE_TENANT_ID -or $env:AZURE_CLIENT_SECRET) {
  Write-Host ("$cross Partial Azure credentials - may cause issues") -ForegroundColor Yellow
} else {
  Write-Host "Using .env file for Azure credentials" -ForegroundColor Gray
}

Write-Host ("$rocket Starting MozaiksAI...") -ForegroundColor Green

if (-not $NoBuild) {
  Write-Host "Building app image..." -ForegroundColor Yellow
  docker build -f infra/docker/Dockerfile -t mozaiksai-app:latest .
  if ($LASTEXITCODE -ne 0) { Write-Host ("$cross Failed to build image") -ForegroundColor Red; exit 1 }
  Write-Host ("$check Image built successfully") -ForegroundColor Green
} else {
  Write-Host ("$skip Skipping build (NoBuild)") -ForegroundColor Yellow
}

Write-Host "Starting services..." -ForegroundColor Yellow
docker compose -f $composeFile up -d
if ($LASTEXITCODE -ne 0) {
  Write-Host "Failed to start services" -ForegroundColor Red
  docker compose -f $composeFile logs --no-color --tail=200
  exit 1
}

Write-Host "Services started successfully!" -ForegroundColor Green
Write-Host ("$globe App available at: http://localhost:8000") -ForegroundColor Cyan

Write-Host ("`n$clip Service Status:") -ForegroundColor Yellow
docker compose -f $composeFile ps
