$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$container = if ($env:LP_POSTGRES_CONTAINER) { $env:LP_POSTGRES_CONTAINER } else { "liangping-postgis" }
$database = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "liangping" }
$user = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "liangping" }
$seed = Join-Path $root "infra\postgres\init\006_seed_demo_layers.sql"
Get-Content $seed -Raw | docker exec -i $container psql -U $user -d $database -v ON_ERROR_STOP=1
Write-Host "PostgreSQL demo seed applied."
