$ErrorActionPreference = "Stop"
$env:DATABASE_URL = if ($env:LP_TEST_DATABASE_URL) { $env:LP_TEST_DATABASE_URL } else { "postgresql://liangping:liangping-db-test-2026@127.0.0.1:55432/liangping" }
$env:LP_PORT = if ($env:LP_TEST_PORT) { $env:LP_TEST_PORT } else { "8879" }
$env:DEMO_MODE = "false"
$env:LP_ENV = "development"
$process = Start-Process python -ArgumentList "backend/server.py" -WorkingDirectory (Get-Location) -PassThru -RedirectStandardOutput "facility-smoke-out.log" -RedirectStandardError "facility-smoke-err.log"
try {
  Start-Sleep -Milliseconds 1200
  $login = Invoke-RestMethod "http://127.0.0.1:$($env:LP_PORT)/api/auth/login" -Method Post -ContentType "application/json" -Body '{"username":"admin","password":"admin123"}'
  $headers = @{ Authorization = "Bearer $($login.token)" }
  $id = "SMOKE-F-$([DateTime]::UtcNow.ToString('HHmmssfff'))"
  $body = @{ facility_id=$id; facility_type="vertiport"; name="CRUD烟测设施"; longitude=107.75; latitude=30.65; status="active"; service_radius_m=500; compatible_vehicles=@("LP-DRONE-01") } | ConvertTo-Json
  $created = Invoke-RestMethod "http://127.0.0.1:$($env:LP_PORT)/api/facilities" -Method Post -Headers $headers -ContentType "application/json" -Body $body
  $updated = Invoke-RestMethod "http://127.0.0.1:$($env:LP_PORT)/api/facilities/$id" -Method Patch -Headers $headers -ContentType "application/json" -Body '{"status":"maintenance","name":"CRUD烟测设施-维护"}'
  $disabled = Invoke-RestMethod "http://127.0.0.1:$($env:LP_PORT)/api/facilities/$id" -Method Delete -Headers $headers
  $audit = Invoke-RestMethod "http://127.0.0.1:$($env:LP_PORT)/api/audit-logs" -Headers $headers
  if ($created.status -ne "active" -or $updated.status -ne "maintenance" -or $disabled.status -ne "disabled" -or -not ($audit | Where-Object { $_.object_id -eq $id }).Count) { throw "facility CRUD assertion failed" }
  @{status="passed"; created=$created.facility_id; updated=$updated.status; disabled=$disabled.status} | ConvertTo-Json -Compress
} finally { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
