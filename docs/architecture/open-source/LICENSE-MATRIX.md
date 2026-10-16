# 开源许可证矩阵

| 组件 | 许可证 | 分发方式 | 需要保留的说明 |
|---|---|---|---|
| MapLibre GL JS 4.7.1 | BSD-3-Clause | 随平台本地 vendor 分发 | 保留 vendor 文件头许可证声明；不将 MapLibre 标识为自研 |
| PostGIS 16-3.4 | PostgreSQL License / 依赖组件各自许可证 | Docker 镜像运行时依赖 | 生产镜像发布时保留镜像及依赖的 notices |
| psycopg 3.x | PostgreSQL License | Python 运行依赖 | 随 Python 依赖清单和部署制品保留许可证信息 |
| OSM/Geofabrik（候选数据） | ODbL | 当前未随运行包导入 | 实际导入时必须保留署名、来源和 ODbL 声明 |

Cesium、Leaflet、OpenLayers、Turf、Three.js 当前没有进入构建或运行包，因此不列入已分发组件。
