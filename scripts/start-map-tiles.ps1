$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$tiles = Join-Path $root "data\openmaptiles\liangping.mbtiles"
if (-not (Test-Path -LiteralPath $tiles -PathType Leaf)) {
  throw "OpenMapTiles数据缺失：$tiles。请先准备覆盖梁平任务区域的授权 .mbtiles 文件。"
}
$composeFile = Join-Path $root "docker-compose.map-tiles.yml"
$compose = Get-Command docker-compose -ErrorAction SilentlyContinue
if ($compose) {
  & $compose.Source -f $composeFile up -d
} else {
  docker compose -f $composeFile up -d
}
if ($LASTEXITCODE -ne 0) { throw "TileServer启动失败，请检查Docker状态和镜像拉取日志。" }
Write-Host "OpenMapTiles TileServer: http://127.0.0.1:8090"
Write-Host "在应用进程设置 LP_MAP_STYLE_URL 为服务实际提供的 style.json 地址后重启应用。"
