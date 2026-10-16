$ErrorActionPreference = "Stop"
$container = if ($env:LP_POSTGRES_CONTAINER) { $env:LP_POSTGRES_CONTAINER } else { "liangping-postgis" }
$database = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "liangping" }
$user = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "liangping" }
$restoreDb = "liangping_restore_p1"
$dumpName = "/tmp/liangping-p1.dump"
$dumpPath = Join-Path $env:TEMP "liangping-p1.dump"

docker exec $container pg_dump -U $user -d $database -Fc -f $dumpName
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed." }
docker cp "$container`:$dumpName" $dumpPath
if (-not (Test-Path -LiteralPath $dumpPath)) { throw "Backup file was not copied." }
docker exec $container psql -U $user -d postgres -v ON_ERROR_STOP=1 -c "drop database if exists $restoreDb;" -c "create database $restoreDb;"
if ($LASTEXITCODE -ne 0) { throw "Restore database creation failed." }
docker cp $dumpPath "$container`:$dumpName"
docker exec $container pg_restore -U $user -d $restoreDb --no-owner --clean --if-exists $dumpName
if ($LASTEXITCODE -ne 0) { throw "pg_restore failed." }
$counts = docker exec $container psql -U $user -d $restoreDb -Atc "select (select count(*) from missions) || '|' || (select count(*) from sessions) || '|' || (select max(version) from schema_migrations);"
docker exec $container psql -U $user -d postgres -v ON_ERROR_STOP=1 -c "drop database if exists $restoreDb;"
if ($LASTEXITCODE -ne 0) { throw "Restore database cleanup failed." }
Write-Host "PostgreSQL restore drill passed: $($counts.Trim())"
