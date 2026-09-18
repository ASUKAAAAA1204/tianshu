$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = @{ Source = "C:\Users\33671\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" } }
& $python.Source -c "import sys; sys.path.insert(0, r'$root\backend'); from db import init_db, database_capabilities; init_db(); print(database_capabilities()); print('Database migration complete')"
