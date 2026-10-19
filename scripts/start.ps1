$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  $pythonPath = "C:\Users\33671\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  if (Test-Path $pythonPath) { $python = @{ Source = $pythonPath } } else { throw "Python 3.10+ was not found." }
}
$env:LP_ENV = "demo"
$env:LP_HOST = "127.0.0.1"
$env:LP_PORT = "8765"
$env:DATABASE_URL = "sqlite:///$root/data/demo-runtime.db"
if (-not $env:LP_MAP_STYLE_URL) { $env:LP_MAP_STYLE_URL = "https://tiles.openfreemap.org/styles/liberty" }
Write-Host "Liangping low-altitude demo: http://127.0.0.1:8765"
Write-Host "Map style: $env:LP_MAP_STYLE_URL"
& $python.Source "$root\backend\server.py"
