# 2D地图 OpenMapTiles 接入阶段记录

**日期**：2026-10-18  
**范围**：MapLibre 2D 底图接入准备，不含 Cesium、3D 或 COMSOL。

## 已完成

- 后端新增只读 `/api/map/config`，由 `LP_MAP_STYLE_URL` 提供可选 TileServer 样式地址。
- MapLibre 启动时校验样式 JSON；只有有效 MapLibre Style v8 才切换到配置的矢量底图。
- TileServer 不可用、地址无效或未配置时继续使用本地 Liangping OSM 参考 GeoJSON，不会退化为空白地图；状态栏区分未配置与服务不可用。
- 使用 OpenMapTiles 时跳过重复的本地道路/水系图层，平台任务、航线、设施和风险覆盖层继续保留。
- 接入 OpenFreeMap 托管样式：默认 `https://tiles.openfreemap.org/styles/liberty`，底层为 OpenMapTiles schema 的矢量源；允许通过环境变量切换 `dark`、`fiord` 等样式。
- CSP 允许访问隔离的 `127.0.0.1:8090` / `localhost:8090` TileServer 资源和 `tiles.openfreemap.org` 在线矢量资源。
- 地图来源标注更新为 `© OpenStreetMap contributors · OpenFreeMap / OpenMapTiles`。
- 新增独立 TileServer Compose 配置和启动脚本，端口为 8090，不占用 8080。
- 新增真实瓦片样式切换的浏览器测试。

## 当前环境核验

- `127.0.0.1:8080` 当前由 MoneyPrinterTurbo 使用，根页面标题为 `MoneyPrinterTurbo`；不是地图服务。
- `http://127.0.0.1:8080/styles/railway/style.json` 返回 404。
- 仓库没有 `.mbtiles` 或 `.pmtiles` 文件，暂时无法验证真实梁平 OpenMapTiles 瓦片视觉效果。
- 在线底图当前可以真实显示；实测 OpenFreeMap `liberty` 样式 111 个样式图层、TileJSON 最大缩放级别 14，梁平中心 Zoom 13 矢量瓦片返回 HTTP 200，约 13.5 KB。
- 本地参考 GeoJSON 仍可加载，用于网络或样式服务不可用时稳定回退；不应误称离线矢量瓦片已准备。
- TileServer 预留端口固定为 `127.0.0.1:8090`。

## 测试结果

- `python -m unittest discover -s tests -q`：40 项通过。
- `npm run test:e2e`：5 项通过，覆盖地图视图、缩放/拖动/图层交互、遥测回放、矢量样式切换和 SVG 回退。
- `LP_E2E_LIVE_MAP=1` 的在线地图专项测试：分别验证 `dark`、`liberty`、`fiord` 样式均可在梁平区域渲染；三种截图用于选择默认样式。
- `node --check`：适配器和 E2E 测试脚本语法通过。
- `docker-compose -f docker-compose.map-tiles.yml config --quiet`：Compose 配置有效。
- 1366×768 Playwright 在线截图：梁平道路、水系、地名、业务航线和业务对象均可见，选择 `liberty` 为默认样式。

## 尚未完成 / 阻断

1. 当前在线底图依赖公网和第三方服务，不提供离线可用性或现场网络保障。
2. 如需比赛现场离线运行，仍需获取并核验覆盖梁平任务区域、具有所需缩放级别的授权 `.mbtiles` 数据，启动本地 TileServer 并设置 `LP_MAP_STYLE_URL`。
3. 当前在线瓦片源 `maxzoom=14`；若需要 15+ 级更多细节，必须更换/自建具有更高 zoom 覆盖的区域瓦片，单纯继续放大不会增加原始数据细节。

在线版本已完成实际底图接入和浏览器渲染验收；离线瓦片部署和高于 Zoom 14 的细节数据仍未完成。
