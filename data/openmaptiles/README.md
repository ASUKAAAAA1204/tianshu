# OpenMapTiles 离线数据

将获得授权并覆盖梁平演示区域的 OpenMapTiles `.mbtiles` 文件放在本目录，文件名固定为：

```text
liangping.mbtiles
```

本仓库不包含瓦片数据库。启动 TileServer 前请先准备数据，并确认数据覆盖任务范围、最大缩放级别和中文字体/样式资源。底图及衍生数据应按其许可保留来源声明；演示业务图层仍需标注“公开参考 / 合成演示数据”。

TileServer 使用回环地址 `127.0.0.1:8090`，避免占用 8080。具体样式路径以服务实际提供的 style 列表为准，可通过环境变量 `LP_MAP_STYLE_URL` 配置，例如：

```text
http://127.0.0.1:8090/styles/basic/style.json
```

