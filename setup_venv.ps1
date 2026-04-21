# Setup virtual environment for Jobright Engine
Write-Host "🚀 Setting up virtual environment..." -ForegroundColor Cyan

if (-not (Test-Path "venv")) {
    python -m venv venv
    Write-Host "✅ Created venv" -ForegroundColor Green
} else {
    Write-Host "ℹ️ venv already exists" -ForegroundColor Yellow
}

Write-Host "📦 Installing dependencies..." -ForegroundColor Cyan
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "✨ Setup complete!" -ForegroundColor Green
Write-Host "To run the scraper: .\venv\Scripts\python.exe run_jobright.py --job-limit 5" -ForegroundColor White
