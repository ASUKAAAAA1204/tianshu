$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$container = if ($env:LP_POSTGRES_CONTAINER) { $env:LP_POSTGRES_CONTAINER } else { "liangping-postgis" }
$database = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "liangping" }
$user = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "liangping" }
$migration = Join-Path $root "infra\postgres\init\006_persistent_sessions.sql"

if (Get-Command docker -ErrorAction SilentlyContinue) {
  Get-Content $migration -Raw | docker exec -i $container psql -U $user -d $database -v ON_ERROR_STOP=1
  $version = docker exec $container psql -U $user -d $database -Atc "select max(version) from schema_migrations;"
} elseif (Get-Command psql -ErrorAction SilentlyContinue) {
  if (-not $env:DATABASE_URL) { throw "未设置 DATABASE_URL，无法连接 PostgreSQL。" }
  Get-Content $migration -Raw | psql $env:DATABASE_URL -v ON_ERROR_STOP=1
  $version = psql $env:DATABASE_URL -Atc "select max(version) from schema_migrations;"
} else {
  throw "未找到 docker 或 psql，无法执行 PostgreSQL 迁移。"
}

if ([int]$version.Trim() -lt 5) { throw "PostgreSQL 迁移未达到版本5，当前版本: $version" }
Write-Host "PostgreSQL migration complete: version $($version.Trim())"
