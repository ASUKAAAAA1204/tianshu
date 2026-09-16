$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $pythonPath = "C:\Users\33671\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"; $python = @{ Source = $pythonPath } }
& $python.Source -c "import sys; sys.path.insert(0, r'$root\backend'); from db import init_db; init_db(reset=True); print('演示数据库已重置')"
