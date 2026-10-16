$ErrorActionPreference = "Stop"
if (Test-Path "data/p0-test.db") { Remove-Item -Force "data/p0-test.db" }
$env:DATABASE_URL = "sqlite:///data/p0-test.db"
$env:LP_PORT = "8876"
$env:DEMO_MODE = "false"
$env:LP_ENV = "development"
$process = Start-Process python -ArgumentList "backend/server.py" -WorkingDirectory (Get-Location) -PassThru -RedirectStandardOutput "p0-out.log" -RedirectStandardError "p0-err.log"
try {
  Start-Sleep -Milliseconds 900
  $health = Invoke-WebRequest "http://127.0.0.1:8876/api/health" -UseBasicParsing
  $login = Invoke-RestMethod "http://127.0.0.1:8876/api/auth/login" -Method Post -ContentType "application/json" -Body '{"username":"admin","password":"admin123"}'
  $headers = @{ Authorization = "Bearer $($login.token)" }
  $me = Invoke-RestMethod "http://127.0.0.1:8876/api/auth/me" -Headers $headers
  $logout = Invoke-RestMethod "http://127.0.0.1:8876/api/auth/logout" -Method Post -Headers $headers
  $afterLogout = 0
  try { Invoke-WebRequest "http://127.0.0.1:8876/api/bootstrap" -UseBasicParsing -ErrorAction Stop | Out-Null } catch { $afterLogout = $_.Exception.Response.StatusCode.value__ }
  @{ health = $health.StatusCode; user = $me.username; logout = $logout.status; after_logout = $afterLogout } | ConvertTo-Json -Compress
}
finally {
  Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
  Remove-Item Env:DATABASE_URL,Env:LP_PORT,Env:DEMO_MODE,Env:LP_ENV -ErrorAction SilentlyContinue
}
