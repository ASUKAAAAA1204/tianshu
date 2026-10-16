# 竞赛基准场景

本目录只保存可重复的合成演示输入，不代表真实授权运行数据。

| 文件 | 场景 | 预期验证 |
|---|---|---|
| `case-hard-zone.json` | 基础设施巡查穿越硬限制区 | 规则拦截与候选绕行 |
| `case-multi-conflict.json` | 同机任务时间窗重叠 | 多任务冲突识别 |
| `case-low-battery.json` | 模拟飞行中低电量告警 | 告警、重规划和人工确认 |

每个场景均包含 `data_version`、`rule_version` 和 `scenario_code`，执行结果由 `scripts/run-benchmark.py` 写入 `docs/evidence/results/`。
