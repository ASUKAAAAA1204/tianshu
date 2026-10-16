# Sprint 6 遥测接入最小闭环

## 目标

让模拟器与后续真实设备适配器共享同一套遥测字段和任务状态更新逻辑，保留人工确认边界，不向真实飞行器发送控制指令。

## 标准字段

`longitude`、`latitude`、`altitude`、`speed`、`heading`、`battery`、`link_quality`、`link`、`status`、`source`、`timestamp`。

其中：

- `source=simulator` 表示离线演示数据；`source=device` 表示设备适配器输入。
- `status` 仅允许 `ready`、`airborne`、`paused`、`completed`、`lost_link`、`landed`。
- 所有坐标、高度、电量和链路质量由服务端再次校验。

## 接口

```http
POST /api/missions/{mission_id}/telemetry
GET  /api/missions/{mission_id}/telemetry
```

示例请求：

```json
{
  "longitude": 107.74,
  "latitude": 30.64,
  "altitude": 120,
  "speed": 12,
  "heading": 90,
  "battery": 58,
  "link_quality": 82,
  "status": "airborne",
  "source": "device",
  "timestamp": "2026-09-18T10:00:00Z"
}
```

## 安全边界

- 遥测接入只更新平台状态、事件和审计，不触发自动飞控。
- 电量低于等于 20% 生成 `low_battery` 告警。
- 链路质量低于 30 或状态为 `lost_link` 生成 `link_loss` 告警。
- 同一任务同一类型的未处置告警只保留一条，避免高频遥测刷屏。
- 旧版本模拟会话缺少新字段时按安全默认值兼容读取。

## 事件驱动重规划

```http
POST /api/missions/{mission_id}/replan
POST /api/replans/{replan_id}/confirm
```

重规划规则：

- 偏航、临时限制区：生成带中间避让点的候选航线。
- 低电量、链路中断：生成当前位置返回任务起点的候选航线。
- 候选航线逐段复核已发布硬限制区，全部不可行时明确返回 `NO_FEASIBLE_REPLAN`。
- 候选方案状态为 `proposed`，只能由管理员或调度员人工确认后变为 `confirmed`。
- 确认人、事件、航线和时间写入 `route_replans` 与 `audit_logs`。
