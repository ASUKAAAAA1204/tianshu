# Third-party notices

## MapLibre GL JS 4.7.1

本项目在 `frontend/vendor/maplibre-gl.js` 和 `frontend/vendor/maplibre-gl.css` 中随包提供 MapLibre GL JS。组件许可证为 BSD-3-Clause；原始文件头保留了项目地址和许可证链接。MapLibre 仅用于二维地图渲染，不代表本项目拥有任何真实空域或测绘数据权利。

## PostGIS / psycopg

PostGIS 通过 `docker-compose.postgres.yml` 的 `postgis/postgis:16-3.4` 镜像运行，psycopg 通过 `requirements-postgres.txt` 安装。部署时应按镜像和 Python 发行包附带的许可证及 notices 一并归档。

## 数据来源边界

当前演示数据标记为 `synthetic_demo` 或公开参考，不把 OSM、Copernicus DEM、SRTM 或政府公开报道误称为已授权运行数据。
