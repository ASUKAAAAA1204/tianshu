$ErrorActionPreference = "Stop"
$env:LP_ENV = "production"
$env:LP_BOOTSTRAP_PASSWORD = "local-validation-bootstrap-2026"
$env:DATABASE_URL = "postgresql://liangping:local-validation-db-2026@127.0.0.1:5432/liangping"
$env:LP_HOST = "127.0.0.1"
$env:LP_PORT = "8765"
$out = Join-Path (Get-Location) "backend-prod-out.log"
$err = Join-Path (Get-Location) "backend-prod-err.log"
Remove-Item $out, $err -Force -ErrorAction SilentlyContinue
$p = Start-Process -FilePath "python" -ArgumentList "-u", "backend/server.py" -WorkingDirectory (Get-Location) -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
$p.Id
