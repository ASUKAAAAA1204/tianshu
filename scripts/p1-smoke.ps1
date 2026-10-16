$ErrorActionPreference = "Stop"
$env:DATABASE_URL = "sqlite:///data/platform.db"
$env:LP_PORT = "8877"
$env:DEMO_MODE = "false"
$env:LP_ENV = "development"
$process = Start-Process python -ArgumentList "backend/server.py" -WorkingDirectory (Get-Location) -PassThru -RedirectStandardOutput "p1-out.log" -RedirectStandardError "p1-err.log"
try {
  Start-Sleep -Milliseconds 900
  python scripts/load-smoke.py http://127.0.0.1:8877 40
  $health = Invoke-WebRequest "http://127.0.0.1:8877/api/health" -UseBasicParsing
  $metricsCode = 0
  try { Invoke-WebRequest "http://127.0.0.1:8877/api/metrics" -UseBasicParsing -ErrorAction Stop | Out-Null } catch { $metricsCode = $_.Exception.Response.StatusCode.value__ }
  @{ health = $health.StatusCode; csp = $health.Headers["Content-Security-Policy"]; metrics_without_login = $metricsCode } | ConvertTo-Json -Compress
}
finally { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
