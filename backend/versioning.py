"""固定运行版本、规则版本和演示数据边界。"""
from __future__ import annotations
import os
ENGINE_VERSION = os.environ.get("LP_ENGINE_VERSION", "0.6.0-recovered")
RULE_VERSION = os.environ.get("LP_RULE_VERSION", "R2026.10.15")
DATA_VERSION = os.environ.get("LP_DATA_VERSION", "DATA-DEMO-20261015")
def traceability() -> dict[str, str | None]:
    return {"engine_version": ENGINE_VERSION, "rule_version": RULE_VERSION, "data_version": DATA_VERSION, "scenario_code": os.environ.get("LP_SCENARIO_CODE", "INFRASTRUCTURE_PATROL"), "valid_time_start": os.environ.get("LP_DATA_VALID_TIME_START", "2026-10-15T00:00:00+08:00"), "valid_time_end": os.environ.get("LP_DATA_VALID_TIME_END") or None}
