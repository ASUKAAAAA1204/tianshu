$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  $pythonPath = "C:\Users\33671\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  if (Test-Path $pythonPath) { $python = @{ Source = $pythonPath } } else { throw "未找到 Python，请安装 Python 3.10+。" }
}
Write-Host "启动梁平低空运行基础底座: http://127.0.0.1:8765"
& $python.Source "$root\backend\server.py"
