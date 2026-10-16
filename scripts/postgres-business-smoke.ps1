$ErrorActionPreference = "Stop"
$env:DATABASE_URL = if ($env:LP_TEST_DATABASE_URL) { $env:LP_TEST_DATABASE_URL } else { "postgresql://liangping:liangping-db-test-2026@127.0.0.1:55432/liangping" }
$env:LP_PORT = if ($env:LP_TEST_PORT) { $env:LP_TEST_PORT } else { "8880" }
$env:DEMO_MODE = "false"; $env:LP_ENV = "development"
$process = Start-Process python -ArgumentList "-u", "backend/server.py" -WorkingDirectory (Get-Location) -PassThru -RedirectStandardOutput "business-smoke-out.log" -RedirectStandardError "business-smoke-err.log"
try {
  Start-Sleep -Milliseconds 1200
  $env:LP_SMOKE_BASE = "http://127.0.0.1:$($env:LP_PORT)"
  python scripts/b3-b4-smoke.py
} finally { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
