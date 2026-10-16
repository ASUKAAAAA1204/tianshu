# 梁平县域数字空域与低空运行智能服务平台

当前版本：`0.5.1`（P0 商用基线加固版）

## 启动

在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

浏览器打开 `http://127.0.0.1:8765`。

默认以生产安全模式启动，需要登录。演示账号为 `admin / admin123`；仅在明确需要免登录演示时设置 `DEMO_MODE=true`，不得用于商用部署。

生产启动请使用 `scripts/start-production.ps1`，并显式设置 `LP_BOOTSTRAP_PASSWORD`（至少12位）；生产模式禁止固定演示密码。会话已落库到 `sessions` 表，支持重启后校验和集中注销。

P1 运维工具：`scripts/db_backup.py`、`scripts/db_restore.py`、`scripts/load-smoke.py`；观测端点为 `/api/metrics`。

P1 运维工具：`scripts/db_backup.py`、`scripts/db_restore.py`、`scripts/load-smoke.py`；观测端点为 `/api/metrics`。

## 当前已落地

- 标准库 Python 后端，提供 `/api/health`、`/api/bootstrap`、图层、飞行器、任务和规则接口。
- 静态运行控制台：空域态势示意、任务状态、规则清单、飞行器资源状态。
- 统一遥测接入、事件告警、候选重规划、人工确认和任务运行时间线。
- 任务证据导出：`GET /api/missions/{id}/replay` 返回结构化回放证据；`GET /api/missions/{id}/report?format=json|html` 导出 JSON 或 HTML 全过程报告。
- 任务支持可选 ISO-8601 时间窗口；规则预检会识别重叠任务，并区分同机/航线相交硬冲突与需人工确认的软冲突。
- `data/demo` 作为演示数据边界，后续可替换为 SQLite、GeoJSON 导入和真实遥测适配器。
- 无外部依赖、可断网启动，符合竞赛现场演示的最低可靠性要求。

## 开发基线

后续实现严格遵循：

1. 先完成 P0 闭环：图层、规则、航线、冲突、事件、人工确认、回放和审计。
2. 不先做农业、应急、物流等行业特例，不做自动飞行控制和审批替代。
3. 每个 Sprint 都保留离线演示路径和可验收产物。

详见 `PRD-梁平低空运行基础底座平台.md` 与 `开发执行基线-梁平低空运行基础底座.md`。
