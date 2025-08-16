# MozaiksAI Startup Script
# Handles the Docker build + compose workflow

Write-Host "🚀 Starting MozaiksAI..." -ForegroundColor Green

# Build the app image (bypasses compose bake issues)
Write-Host "Building app image..." -ForegroundColor Yellow
docker build -f infra/docker/Dockerfile -t mozaiksai-app:latest .

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Image built successfully" -ForegroundColor Green
    
    # Start services
    Write-Host "Starting services..." -ForegroundColor Yellow
    docker compose -f infra/compose/docker-compose.yml up -d
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Services started successfully!" -ForegroundColor Green
        Write-Host "🌐 App available at: http://localhost:8000" -ForegroundColor Cyan
        Write-Host "📊 MongoDB at: localhost:27017" -ForegroundColor Cyan
        
        # Show running containers
        Write-Host "`n📋 Service Status:" -ForegroundColor Yellow
        docker compose -f infra/compose/docker-compose.yml ps
    } else {
        Write-Host "❌ Failed to start services" -ForegroundColor Red
    }
} else {
    Write-Host "❌ Failed to build image" -ForegroundColor Red
}
