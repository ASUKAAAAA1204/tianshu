"""标准遥测模型与运行态告警判定。

模拟器和真实设备都必须先经过这里，保证任务状态机只消费统一字段。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class TelemetryError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _number(payload: dict[str, Any], key: str, minimum: float, maximum: float) -> float:
    try:
        value = float(payload[key])
    except (KeyError, TypeError, ValueError) as error:
        raise TelemetryError("INVALID_TELEMETRY", f"{key} 必须为数字") from error
    if not minimum <= value <= maximum:
        raise TelemetryError("INVALID_TELEMETRY", f"{key} 超出允许范围")
    return value


def normalize_telemetry(payload: dict[str, Any], *, default_source: str = "simulator") -> dict[str, Any]:
    """将设备或模拟器输入归一化为可审计的标准遥测记录。"""
    if not isinstance(payload, dict):
        raise TelemetryError("INVALID_TELEMETRY", "遥测载荷必须是 JSON 对象")
    source = str(payload.get("source", default_source)).strip() or default_source
    timestamp = payload.get("timestamp")
    if timestamp:
        try:
            parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            timestamp = parsed.astimezone(timezone.utc).isoformat()
        except ValueError as error:
            raise TelemetryError("INVALID_TIMESTAMP", "timestamp 必须是 ISO-8601 时间") from error
    else:
        timestamp = datetime.now(timezone.utc).isoformat()
    link_quality = _number(payload, "link_quality", 0, 100) if "link_quality" in payload else 100.0
    battery = _number(payload, "battery", 0, 100)
    status = str(payload.get("status", "airborne"))
    if status not in {"ready", "airborne", "paused", "completed", "lost_link", "landed"}:
        raise TelemetryError("INVALID_STATUS", "不支持的飞行状态")
    return {
        "longitude": _number(payload, "longitude", 105, 110),
        "latitude": _number(payload, "latitude", 28, 32),
        "altitude": _number(payload, "altitude", 0, 1200),
        "speed": _number(payload, "speed", 0, 150) if "speed" in payload else 0.0,
        "heading": _number(payload, "heading", 0, 360) if "heading" in payload else 0.0,
        "battery": round(battery, 1),
        "link_quality": round(link_quality, 1),
        "link": "offline" if status == "lost_link" or link_quality < 10 else "online",
        "status": status,
        "source": source,
        "timestamp": timestamp,
    }


def runtime_alerts(telemetry: dict[str, Any]) -> list[dict[str, str]]:
    """根据遥测生成可解释告警；只产生建议，不触发任何飞控动作。"""
    alerts: list[dict[str, str]] = []
    if float(telemetry.get("battery", 100)) <= 20:
        alerts.append({"event_type": "low_battery", "severity": "critical", "message": "飞行器电量不足"})
    if telemetry.get("link", "online") == "offline" or float(telemetry.get("link_quality", 100)) < 30:
        alerts.append({"event_type": "link_loss", "severity": "critical", "message": "飞行器链路质量下降或中断"})
    if telemetry.get("status", "airborne") == "paused":
        alerts.append({"event_type": "deviation", "severity": "warning", "message": "飞行器处于暂停状态，需人工确认"})
    return alerts
