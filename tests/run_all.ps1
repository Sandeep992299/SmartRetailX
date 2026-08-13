Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Starting SmartRetailX Unified Test Suite" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Ensure k6 and Bruno paths are loaded in PowerShell
$env:PATH += ";C:\Program Files\k6"

# 1. Run Unit Tests (Mocked MongoDB, Redis, Postgres, Kafka, Prometheus)
Write-Host "`n[1/5] Running Unit Tests..." -ForegroundColor Yellow
pytest tests/unit -v --cov=tests/unit --cov-report=term
if ($LASTEXITCODE -ne 0) { 
    Write-Error "Unit testing failed! Exiting pipeline."
    exit 1 
}

# 2. Run Integration Service Tests (Requires active EKS port-forward)
Write-Host "`n[2/5] Running Integration Service Tests..." -ForegroundColor Yellow
pytest tests/test_services.py -v --tb=short
if ($LASTEXITCODE -ne 0) { 
    Write-Warning "Integration service tests failed or EKS port-forward is inactive."
}

# 3. Run Security & OWASP Verification Tests
Write-Host "`n[3/5] Running OWASP Security Verification Tests..." -ForegroundColor Yellow
pytest tests/test_security.py -v --tb=short
if ($LASTEXITCODE -ne 0) { 
    Write-Error "Security verification tests failed! Exiting pipeline."
    exit 1 
}

# 4. Run Bruno API Contract Verification (Requires Bruno CLI installed)
Write-Host "`n[4/5] Running Bruno API Contract Validation..." -ForegroundColor Yellow
if (Get-Command bru -ErrorAction SilentlyContinue) {
    cd tests/bruno
    bru run --env Local
    cd ..\..
} else {
    Write-Warning "Bruno CLI not found. Skipping Bruno API Contract Validation."
}

# 5. Run k6 Load & Stress Simulation (Requires k6 CLI installed)
Write-Host "`n[5/5] Running k6 Load & Performance Simulation..." -ForegroundColor Yellow
if (Get-Command k6 -ErrorAction SilentlyContinue) {
    k6 run tests/k6_load_test.js
} else {
    Write-Warning "k6 CLI not found. Skipping Load Simulation."
}

Write-Host "`n=========================================" -ForegroundColor Green
Write-Host "SmartRetailX Unified Test Suite Complete!" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
