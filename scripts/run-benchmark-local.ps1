$ErrorActionPreference = "Stop"
$db = "data/benchmark-round2.db"
$out = Join-Path $env:TEMP "lp-benchmark-out.log"
$err = Join-Path $env:TEMP "lp-benchmark-err.log"
if (Test-Path -LiteralPath $db) { Remove-Item -LiteralPath $db -Force }
$env:DATABASE_URL = "sqlite:///$db"
$env:LP_PORT = "8877"
$env:DEMO_MODE = "false"
$env:LP_ENV = "development"
$env:LP_BOOTSTRAP_PASSWORD = "benchmark-pass-2026"
$process = Start-Process python -ArgumentList "-u backend/server.py" -WorkingDirectory (Get-Location) -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
try {
  Start-Sleep -Milliseconds 1100
  python scripts/run-benchmark.py http://127.0.0.1:8877 --password benchmark-pass-2026 --output docs/evidence/results/benchmark-summary.json
}
finally {
  Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $db -Force -ErrorAction SilentlyContinue
  Remove-Item Env:DATABASE_URL,Env:LP_PORT,Env:DEMO_MODE,Env:LP_ENV,Env:LP_BOOTSTRAP_PASSWORD -ErrorAction SilentlyContinue
}
if (Test-Path -LiteralPath $err) {
  $stderr = Get-Content -LiteralPath $err -Raw
  if (-not [string]::IsNullOrWhiteSpace($stderr)) { Write-Error $stderr }
}
