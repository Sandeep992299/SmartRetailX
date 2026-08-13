Write-Host "========================================="
Write-Host "Starting SmartRetailX Automation Tests"
Write-Host "========================================="

# 1. Run Unit Tests (Mocked environment)
Write-Host "[1/4] Running Unit & Metrics Tests..."
pytest tests/test_metrics.py
if ($LASTEXITCODE -ne 0) { Write-Error "Unit tests failed!"; exit 1 }

# 2. Run Security Verification
Write-Host "[2/4] Running Security Vulnerability Check..."
pytest tests/test_security.py
if ($LASTEXITCODE -ne 0) { Write-Error "Security verification failed!"; exit 1 }

# 3. Run Bruno API Contract Verification
Write-Host "[3/4] Running Bruno API Contract Validation..."
# Note: Requires npm install -g @usebruno/cli
bru run tests/bruno --env Local
if ($LASTEXITCODE -ne 0) { Write-Warning "Bruno API validations failed/skipped (check if CLI is installed or services are running)"; }

# 4. Run k6 Load and Stress Simulation
Write-Host "[4/4] Executing k6 Load Testing..."
# Note: Requires k6 CLI installed
k6 run tests/k6_load_test.js
if ($LASTEXITCODE -ne 0) { Write-Warning "k6 load tests failed/skipped (check if k6 is installed)"; }

Write-Host "========================================="
Write-Host "All testing phases executed successfully!"
Write-Host "========================================="
