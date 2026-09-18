# PostgreSQL/PostGIS 全量迁移计划

## 1. 目标

在不破坏 SQLite 离线演示模式的前提下，完成 PostgreSQL/PostGIS 生产数据底座准备，覆盖：

1. PostgreSQL/PostGIS 初始化脚本。
2. PostgreSQL 版本迁移 SQL。
3. 数据库连接健康检查。
4. 图层空间字段与空间索引。
5. 生产环境使用 `ST_Intersects`。
6. SQLite / PostgreSQL 双后端集成测试。

目标架构：

```text
SQLite 离线模式 ─┐
                 ├─ 统一仓储接口 ─ 统一规则服务 ─ 统一 HTTP API
PostgreSQL/PostGIS┘
```

## 2. 原则

- SQLite 继续作为比赛和无网络场景的离线后端。
- PostgreSQL/PostGIS 作为封闭试点和生产目标后端。
- 没有连接验证、迁移验证和回滚验证前，不切换默认后端。
- 业务接口不感知数据库差异。
- SQLite 使用 Python Polygon；PostGIS 使用 `ST_Intersects`。
- 真实、演示、迁移数据明确区分。
- 每个数据库变更都有版本号、校验和、回滚说明。

## 3. 阶段总览

| 阶段 | 主题 | 主要结果 | 退出条件 |
|---|---|---|---|
| A | 数据库基线 | PostgreSQL/PostGIS 初始化 | 容器可启动、扩展可用 |
| B | 迁移体系 | PostgreSQL 版本迁移和回滚 | 重复执行无副作用 |
| C | 连接治理 | 连接池、健康检查、故障报告 | 连接失败可解释 |
| D | 空间模型 | geometry 字段、SRID、空间索引 | 空间查询可执行 |
| E | 空间规则 | `ST_Intersects` 规则服务 | 生产规则不依赖包围盒 |
| F | 双后端质量 | SQLite/PostGIS 集成测试 | 结果一致或差异可解释 |

## 4. 阶段 A：初始化环境

新增目录和文件：

```text
infra/postgres/init/001_extensions.sql
infra/postgres/init/002_schema.sql
infra/postgres/init/003_seed_roles.sql
docker-compose.postgres.yml
```

初始化扩展：

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

同步当前表：

```text
layers, vehicles, rules, missions, audit_logs,
mission_checks, routes, flight_sessions, events,
users, schema_migrations
```

类型映射：

| SQLite | PostgreSQL |
|---|---|
| INTEGER AUTOINCREMENT | BIGSERIAL |
| TEXT | TEXT |
| REAL | DOUBLE PRECISION |
| CURRENT_TIMESTAMP | TIMESTAMPTZ |
| geometry_json | JSONB |
| 新增几何字段 | geometry(Geometry,4326) |

验收：容器可启动、`postgis_full_version()` 可执行、表和迁移记录成功创建。

## 5. 阶段 B：迁移与回滚

目录：

```text
migrations/sqlite/
migrations/postgres/
```

命名：

```text
V001__initial_schema.sql
V002__audit_actor.sql
V003__login_lockout.sql
V004__spatial_columns.sql
V005__spatial_indexes.sql
```

迁移记录至少保存：

- version
- name
- checksum
- applied_at
- execution_ms

规则：

- 迁移失败不得标记成功。
- 删除字段、改变类型必须提供显式 down SQL。
- 空间字段迁移必须保留 JSONB 原始字段。
- 迁移前自动执行结构备份。
- 连续执行两次不得产生重复变更。

## 6. 阶段 C：连接治理

支持配置：

```text
DATABASE_URL
DB_POOL_MIN
DB_POOL_MAX
DB_CONNECT_TIMEOUT
DB_STATEMENT_TIMEOUT
```

PostgreSQL 使用 `psycopg_pool` 或等效连接池，要求连接数、超时和关闭行为可配置。

新增深度健康接口：

```http
GET /api/health/deep
```

返回：

- 应用进程状态。
- 数据库连接状态。
- PostGIS 扩展状态。
- 当前迁移版本。
- 空间查询探针结果。
- 最近错误摘要。

状态统一为：

```text
ready / degraded / unavailable / migration_required
```

数据库停止、PostGIS缺失或迁移落后时不得误报 `ready`。

## 7. 阶段 D：空间字段与索引

PostgreSQL `layers` 增加：

```sql
geometry geometry(Geometry,4326) NOT NULL;
min_altitude_m DOUBLE PRECISION;
max_altitude_m DOUBLE PRECISION;
valid_from TIMESTAMPTZ;
valid_to TIMESTAMPTZ;
```

保留：

```text
geometry_json JSONB
```

导入流程：

```text
GeoJSON接收
→ JSON格式校验
→ Geometry转换
→ SRID设置4326
→ ST_IsValid校验
→ 区域范围校验
→ 写入geometry和geometry_json
→ 记录来源与版本
```

空间索引：

```sql
CREATE INDEX idx_layers_geometry_gist
ON layers USING GIST (geometry);
```

发布前必须验证几何有效、SRID正确、类型正确、坐标范围合法、Polygon闭合。

## 8. 阶段 E：PostGIS 规则服务

统一内部接口：

```python
check_route_against_layers(route, layers, context) -> RuleResult
```

SQLite 实现调用 `backend/geometry.py`；PostgreSQL 实现使用参数化 SQL：

```sql
SELECT id, name, layer_type, level
FROM layers
WHERE status = 'published'
  AND ST_Intersects(
        geometry,
        ST_SetSRID(ST_MakeLine(
          ST_MakePoint(%s, %s),
          ST_MakePoint(%s, %s)
        ), 4326)
      );
```

同时判断：

- 计划高度与图层高度区间。
- 任务时间与有效窗口。
- 当前发布版本。
- 图层可信等级。

统一返回：

```json
{
  "decision": "blocked",
  "risk_level": "high",
  "engine": "postgis",
  "items": []
}
```

生产规则不得继续使用矩形包围盒近似。

## 9. 阶段 F：双后端测试

测试层级：

### 单元测试

- URL解析。
- 配置状态。
- Polygon几何。
- 规则结果结构。
- 迁移版本。

### SQLite 集成测试

- 初始化、种子、任务创建、规则检查、航线规划、事件处置。

### PostgreSQL 集成测试

使用 Docker Compose 启动 PostGIS，执行同一套业务测试。

固定基准用例：

1. 合法直连任务。
2. 穿越硬限制区。
3. 命中软限制区。
4. 不规则 Polygon 外接矩形误报场景。

比较：decision、risk_level、规则编码、图层ID、距离和耗时容差。

通过标准：关键结果一致率100%，空间误报和漏报基准为0；PostgreSQL停止时明确失败，不静默回退 SQLite。

## 10. 文件计划

预计新增：

```text
infra/postgres/init/001_extensions.sql
infra/postgres/init/002_schema.sql
infra/postgres/init/003_seed.sql
infra/postgres/docker-compose.yml
migrations/sqlite/V004__spatial_metadata.sql
migrations/postgres/V001__initial_schema.sql
migrations/postgres/V002__spatial_columns.sql
migrations/postgres/V003__spatial_indexes.sql
backend/repository_postgres.py
backend/spatial_repository.py
tests/test_dual_backend.py
scripts/check-db.ps1
```

## 11. 实施顺序

1. 建立 PostgreSQL/PostGIS Docker 环境。
2. 编写初始化 SQL。
3. 接入 PostgreSQL 迁移记录和版本校验。
4. 完成连接池和深度健康检查。
5. 增加 geometry 字段与 GIST 索引。
6. 实现空间仓储接口。
7. 将规则服务切换为后端无关接口。
8. 接入 PostGIS `ST_Intersects`。
9. 执行双后端基准测试。
10. 通过质量门禁后才允许试点环境切换。

## 12. 回滚与阻断

- 生产切换前始终保留 SQLite 离线模式。
- PostGIS异常时返回 `degraded`，不静默切换到错误数据源。
- 迁移失败保留当前版本，不标记成功。
- Geometry 转换失败保留 JSONB 原始数据。

以下任一条件未满足，不得进入生产切换：

- PostGIS 扩展不可用。
- 迁移版本无法追踪。
- 空间索引未创建。
- 双后端结果不一致。
- 健康检查误报 `ready`。
- PostgreSQL停止时系统静默回退 SQLite。

## 13. 最终交付物

- 可重复启动的 PostGIS 环境。
- 可重复执行的数据库迁移。
- 深度健康检查。
- 含空间字段和索引的图层表。
- 统一空间规则接口。
- SQLite/PostGIS 双后端测试报告。
- 数据迁移和回滚操作手册。
- 试点环境配置模板。
