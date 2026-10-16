# 开源组件嵌入清单

更新时间：2026-10-16

本清单只把“代码或运行环境中实际加载、且有验证证据”的组件标记为已嵌入；方案文档、网络链接或未来计划不算嵌入。

| 组件 | 版本/来源 | 实际嵌入位置 | 当前用途 | 状态 |
|---|---|---|---|---|
| MapLibre GL JS | v4.7.1，本地 vendor | `frontend/vendor/maplibre-gl.js`、`frontend/vendor/maplibre-gl.css`、`frontend/adapters/maplibre-adapter.js` | 二维任务地图、缩放、拖拽、图层和航线叠加 | 已嵌入并经 Playwright 截图验证 |
| PostGIS | `postgis/postgis:16-3.4` | `docker-compose.postgres.yml`、`infra/postgres/init/001_extensions.sql` | PostgreSQL 空间底座和空间探针 | 已嵌入并经容器/业务烟测验证 |
| psycopg | `requirements-postgres.txt`，3.x | `backend/repository.py`、`backend/db.py` | PostgreSQL 连接和事务适配 | 已嵌入并经 PostgreSQL 业务烟测验证 |
| MapLibre adapter boundary | 项目适配层，不是第三方库 | `frontend/adapters/map-adapter.js` | 隔离地图引擎，保留 SVG 离线回退 | 已完成 |
| CesiumJS | 计划中的决赛三维组件 | 无 vendor、无入口、无运行时加载 | 三维地形/建筑/路径演示 | 未嵌入，按本轮范围排除 |
| Leaflet / OpenLayers | 早期备选方案 | 无依赖、无入口 | 未采用 | 未嵌入 |
| Turf.js / Three.js | 规划中的空间/三维扩展 | 无依赖、无入口 | 未采用 | 未嵌入 |

## 验收证据

- `python scripts/oss-embedding-smoke.py`：检查清单中的本地文件、入口引用、版本标识和禁止误报组件。
- `npm run test:e2e -- tests/e2e/debug-map.spec.cjs`：验证 MapLibre 初始化、地图交互和航线显示。
- `scripts/p1-postgres-smoke.ps1`、`scripts/postgres-business-smoke.ps1`：验证 PostGIS/psycopg 实际连接和业务闭环。

## 边界

- 当前地图使用本地 MapLibre 引擎和本地合成/公开参考数据，不依赖外部瓦片服务。
- OSM、Copernicus DEM、SRTM、Open-Meteo 是数据来源候选或数据治理对象，不是当前已嵌入的第三方运行库；没有实际导入的数据不得标记为已接入。
- CesiumJS、三维建筑、三维路径搜索和 AI 优化属于决赛专项，不在本轮二维平台恢复验收内。
