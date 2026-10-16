$ErrorActionPreference = "Stop"
$env:DATABASE_URL = if ($env:LP_TEST_DATABASE_URL) { $env:LP_TEST_DATABASE_URL } else { "postgresql://liangping:P1-Validation-Only-2026!@127.0.0.1:5432/liangping" }
$env:LP_PORT = if ($env:LP_TEST_PORT) { $env:LP_TEST_PORT } else { "8878" }
$env:DEMO_MODE = "false"
$env:LP_ENV = "development"
$process = Start-Process python -ArgumentList "backend/server.py" -WorkingDirectory (Get-Location) -PassThru -RedirectStandardOutput "pg-smoke-out.log" -RedirectStandardError "pg-smoke-err.log"
try {
  Start-Sleep -Milliseconds 1200
  $health = Invoke-RestMethod "http://127.0.0.1:8878/api/health"
  $login = Invoke-RestMethod "http://127.0.0.1:8878/api/auth/login" -Method Post -ContentType "application/json" -Body '{"username":"admin","password":"admin123"}'
  $headers = @{ Authorization = "Bearer $($login.token)" }
  $deep = Invoke-RestMethod "http://127.0.0.1:8878/api/health/deep" -Headers $headers
  $bootstrap = Invoke-RestMethod "http://127.0.0.1:8878/api/bootstrap" -Headers $headers
  $metrics = Invoke-RestMethod "http://127.0.0.1:8878/api/metrics" -Headers $headers
  @{ health = $health.status; backend = $health.database.adapter; deep = $deep.status; migration = $deep.deep.migration_version; layers = $bootstrap.layers.Count; missions = $bootstrap.missions.Count; metrics = $metrics.status } | ConvertTo-Json -Compress
}
finally { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
