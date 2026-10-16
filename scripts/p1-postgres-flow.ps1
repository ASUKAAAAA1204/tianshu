$ErrorActionPreference = "Stop"
$env:DATABASE_URL = if ($env:LP_TEST_DATABASE_URL) { $env:LP_TEST_DATABASE_URL } else { "postgresql://liangping:P1-Validation-Only-2026!@127.0.0.1:5432/liangping" }
$env:LP_PORT = if ($env:LP_TEST_PORT) { $env:LP_TEST_PORT } else { "8879" }
$env:DEMO_MODE = "false"
$env:LP_ENV = "development"
$process = Start-Process python -ArgumentList "-u backend/server.py" -WorkingDirectory (Get-Location) -PassThru -RedirectStandardOutput "pg-flow-out.log" -RedirectStandardError "pg-flow-err.log"
try {
  Start-Sleep -Milliseconds 1200
  $login = Invoke-RestMethod "http://127.0.0.1:$($env:LP_PORT)/api/auth/login" -Method Post -ContentType "application/json" -Body '{"username":"admin","password":"admin123"}'
  $headers = @{ Authorization = "Bearer $($login.token)" }
  $id = "MS-P1-$([DateTime]::UtcNow.ToString('HHmmssfff'))"
  $payload = @{ id=$id; name="PostgreSQL P1 联调任务"; vehicle_id="UAV-LP-001"; route_name="R-P1-01"; start_lng=107.700; start_lat=30.700; end_lng=107.720; end_lat=30.720; planned_altitude=120 } | ConvertTo-Json -Compress
  $base = "http://127.0.0.1:$($env:LP_PORT)"
  $created = Invoke-RestMethod "$base/api/missions" -Method Post -Headers $headers -ContentType "application/json" -Body $payload
  $check = Invoke-RestMethod "$base/api/missions/$id/check" -Method Post -Headers $headers -ContentType "application/json" -Body '{}'
  $route = Invoke-RestMethod "$base/api/missions/$id/routes/plan" -Method Post -Headers $headers -ContentType "application/json" -Body '{}'
  $flight = Invoke-RestMethod "$base/api/missions/$id/flight/start" -Method Post -Headers $headers -ContentType "application/json" -Body '{}'
  $tick = Invoke-RestMethod "$base/api/missions/$id/flight/tick" -Method Post -Headers $headers -ContentType "application/json" -Body '{"step":10}'
  @{ mission=$created.id; check=$check.decision; route=$route.id; flight=$flight.status; tick_progress=$tick.progress } | ConvertTo-Json -Compress
}
finally { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
