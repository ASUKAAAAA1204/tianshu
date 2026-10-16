# PostgreSQL 应用链路验证记录

## 验证信息

- 验证日期：2026-09-19
- 容器：`liangping-postgis`
- 镜像：`postgis/postgis:16-3.4`
- 宿主端口：`55432`
- 数据库：`liangping`
- 迁移版本：`16`
- 运行版本：`0.6.1-p0`

## 验证结果

| 项目 | 结果 | 实测证据 |
|---|---|---|
| 容器健康检查 | 通过 | Docker 状态为 `healthy` |
| 用户初始化 | 通过 | `bootstrap-postgres.ps1` 从 `LP_BOOTSTRAP_PASSWORD` 写入 4 个角色 |
| 应用健康检查 | 通过 | `backend=postgresql`、`health=ok` |
| 深度健康检查 | 通过 | `deep=ready`、PostGIS 探针成功 |
| 迁移门禁 | 通过 | `migration=16` |
| 登录与会话 | 通过 | 管理员登录返回 token |
| Bootstrap 与指标 | 通过 | `layers=3`、`missions=9`、`metrics=ok` |
| 任务业务流 | 通过 | 创建任务、规则检查、航线规划、启动飞行、Tick 10% 全部成功 |
| 备份恢复 | 通过 | 恢复库返回 `10|3|16`（任务、会话、迁移版本） |

## 结论与边界

P0-5 的隔离 PostgreSQL/PostGIS 应用链路已通过。该证据不等于正式商业交付，TLS、反向代理、多实例、集中式会话/限流和 24 小时稳定性仍需单独验收。
