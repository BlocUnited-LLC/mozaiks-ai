# ==============================================================================
# MozaiksAI - Deep Cleanse Script
# Removes all cache, build artifacts, logs, and optionally runtime state
# ==============================================================================

param(
    [switch]$KeepLogs,
    [switch]$KeepDB,
    [switch]$Full
)

Write-Host " Starting MozaiksAI deep cleanse..." -ForegroundColor Cyan

# Python bytecode and __pycache__
Write-Host "`n Cleaning Python bytecode..." -ForegroundColor Yellow
Get-ChildItem -Path "." -Include "*.pyc" -Recurse -Force -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem -Path "." -Include "__pycache__" -Recurse -Directory -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Write-Host "    Removed *.pyc and __pycache__ directories" -ForegroundColor Green

# React/Webpack build artifacts and cache
Write-Host "`n  Cleaning React/Webpack artifacts..." -ForegroundColor Yellow
if (Test-Path "ChatUI") {
    Push-Location ChatUI
    Remove-Item -Recurse -Force .cache, node_modules/.cache, build -ErrorAction SilentlyContinue
    Pop-Location
    Write-Host "    Removed ChatUI/.cache, node_modules/.cache, build/" -ForegroundColor Green
}

# Logs (optional)
if (-not $KeepLogs) {
    Write-Host "`n Cleaning logs..." -ForegroundColor Yellow
    if (Test-Path "logs/logs") {
        Get-ChildItem -Path "logs/logs" -Filter "*.log" -ErrorAction SilentlyContinue | Remove-Item -Force
        Write-Host "    Removed logs/logs/*.log" -ForegroundColor Green
    }
} else {
    Write-Host "`n Keeping logs (-KeepLogs flag set)" -ForegroundColor Gray
}

# MongoDB collections cleanup (clears documents only, preserves collections/indexes)
if (-not $KeepDB) {
    Write-Host "`n🗄️  Clearing MongoDB collections (documents only)..." -ForegroundColor Yellow
    $clearScript = Join-Path -Path $PSScriptRoot -ChildPath "clear_collections.py"
    if (Test-Path $clearScript) {
        # Run with .venv Python to ensure pymongo is available
        $pythonCmd = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
        $output = & $pythonCmd $clearScript --action delete --yes 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   ✅ Cleared MongoDB documents (collections/indexes preserved)" -ForegroundColor Green
        } else {
            Write-Host "   ⚠️  Failed to clear collections:" -ForegroundColor Yellow
            Write-Host "      $output" -ForegroundColor Gray
        }
    } else {
        Write-Host "   ⚠️  clear_collections.py not found, skipping collection cleanup" -ForegroundColor Gray
    }
} else {
    Write-Host "`n🗄️  Keeping MongoDB data (-KeepDB flag set)" -ForegroundColor Gray
}

# Docker cleanup (optional - VERY DESTRUCTIVE)
if ($Full) {
    Write-Host "`n Cleaning Docker containers and images..." -ForegroundColor Yellow
    
    # Stop and remove ALL containers (running or stopped)
    $allContainers = docker ps -aq 2>$null
    if ($allContainers) {
        docker stop $allContainers 2>$null | Out-Null
        docker rm $allContainers 2>$null | Out-Null
        Write-Host "    Stopped and removed all Docker containers" -ForegroundColor Green
    } else {
        Write-Host "    No containers to remove" -ForegroundColor Gray
    }
    
    # Remove ALL images
    $allImages = docker images -q 2>$null
    if ($allImages) {
        docker rmi -f $allImages 2>$null | Out-Null
        Write-Host "    Removed all Docker images" -ForegroundColor Green
    } else {
        Write-Host "    No images to remove" -ForegroundColor Gray
    }
    
    # Prune everything (containers, networks, images, build cache)
    docker system prune -af --volumes 2>$null | Out-Null
    Write-Host "    Docker system pruned (build cache, networks, volumes)" -ForegroundColor Green
}

# Optional: .venv cache (Python pip cache)
if ($Full) {
    Write-Host "`n Cleaning Python pip cache..." -ForegroundColor Yellow
    if (Test-Path ".venv") {
        python -m pip cache purge 2>$null | Out-Null
        Write-Host "    Python pip cache purged" -ForegroundColor Green
    }
}

Write-Host "`n Cleanse complete!`n" -ForegroundColor Cyan

# Show usage if not running with Full flag
if (-not $Full) {
    Write-Host " Tip: Run with -Full flag for deeper cleaning (DB, Docker cache, pip cache)" -ForegroundColor Gray
    Write-Host "   Example: .\scripts\cleanse.ps1 -Full" -ForegroundColor Gray
    Write-Host "   Flags: -KeepLogs, -KeepDB, -Full`n" -ForegroundColor Gray
}
