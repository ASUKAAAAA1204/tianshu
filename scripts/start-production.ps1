$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $env:LP_ENV) { $env:LP_ENV = "production" }
if (-not $env:LP_BOOTSTRAP_PASSWORD -or $env:LP_BOOTSTRAP_PASSWORD.Length -lt 12) {
  throw "生产启动前必须设置 LP_BOOTSTRAP_PASSWORD，且长度不少于12位。"
}
if (-not $env:LP_HOST) { $env:LP_HOST = "127.0.0.1" }
if (-not $env:LP_PORT) { $env:LP_PORT = "8765" }
$python = Get-Command python -ErrorAction Stop
Write-Host "Starting production backend on $($env:LP_HOST):$($env:LP_PORT)"
& $python.Source "$root\backend\server.py"
