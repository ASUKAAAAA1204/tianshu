"""Explicit, cached queries to the public Open-Meteo elevation reference API."""

from __future__ import annotations

import json
import math
import threading
import time
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://api.open-meteo.com/v1/elevation"
USER_AGENT = "LiangpingLowAltitudePlatform/0.6 (public elevation reference)"
MAX_POINTS = 50
MAX_ROUTE_SAMPLES = 50
CACHE_TTL_SECONDS = 24 * 60 * 60
CACHE_MAX_ENTRIES = 2000
_CACHE: dict[tuple[float, float], tuple[float, float, str]] = {}
_CACHE_LOCK = threading.Lock()
_UPSTREAM_LOCK = threading.Lock()
_LAST_UPSTREAM_REQUEST = 0.0


class ElevationProviderError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _distance_m(left: list[float], right: list[float]) -> float:
    radius = 6_371_000
    lat1, lat2 = math.radians(left[1]), math.radians(right[1])
    dlat, dlon = lat2 - lat1, math.radians(right[0] - left[0])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def sample_route(points: list[list[float]], max_points: int = MAX_ROUTE_SAMPLES) -> list[list[float]]:
    if not isinstance(points, list) or not points:
        raise ElevationProviderError("INVALID_ROUTE", "航线坐标不能为空")
    normalized = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            raise ElevationProviderError("INVALID_COORDINATE", "航线坐标格式无效")
        try:
            lng, lat = float(point[0]), float(point[1])
        except (TypeError, ValueError) as error:
            raise ElevationProviderError("INVALID_COORDINATE", "航线经纬度必须为数字") from error
        if not 107.4 <= lng <= 108.0 or not 30.3 <= lat <= 31.0:
            raise ElevationProviderError("OUT_OF_REFERENCE_AREA", "高程参考查询仅覆盖梁平演示区域附近")
        normalized.append([lng, lat])
    if len(normalized) == 1:
        return normalized
    total = sum(_distance_m(left, right) for left, right in zip(normalized, normalized[1:]))
    spacing = max(1000.0, total / max(1, max_points - 1))
    result = []
    for left, right in zip(normalized, normalized[1:]):
        count = max(1, math.ceil(_distance_m(left, right) / spacing))
        for index in range(count):
            ratio = index / count
            result.append([left[0] + (right[0] - left[0]) * ratio, left[1] + (right[1] - left[1]) * ratio])
    result.append(normalized[-1])
    if len(result) > max_points:
        stride = (len(result) - 1) / (max_points - 1)
        result = [result[round(index * stride)] for index in range(max_points - 1)] + [result[-1]]
    return result


def fetch_elevations(points: list[list[float]], timeout: float = 8.0) -> dict:
    if not isinstance(points, list) or not points or len(points) > MAX_POINTS:
        raise ElevationProviderError("INVALID_SAMPLE_COUNT", f"高程采样数量须为 1 至 {MAX_POINTS} 个")
    normalized = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            raise ElevationProviderError("INVALID_COORDINATE", "采样坐标格式无效")
        try:
            lng, lat = float(point[0]), float(point[1])
        except (TypeError, ValueError) as error:
            raise ElevationProviderError("INVALID_COORDINATE", "采样经纬度必须为数字") from error
        if not 107.4 <= lng <= 108.0 or not 30.3 <= lat <= 31.0:
            raise ElevationProviderError("OUT_OF_REFERENCE_AREA", "高程参考查询仅覆盖梁平演示区域附近")
        normalized.append([lng, lat])

    now = datetime.now(timezone.utc)
    now_epoch = now.timestamp()
    keys = [(round(lng, 5), round(lat, 5)) for lng, lat in normalized]
    with _CACHE_LOCK:
        cached = {key: value for key, value in _CACHE.items() if now_epoch - value[1] < CACHE_TTL_SECONDS}
        _CACHE.clear()
        _CACHE.update(cached)
        missing = list(dict.fromkeys(key for key in keys if key not in _CACHE))
    retrieved_at = now.isoformat()
    global _LAST_UPSTREAM_REQUEST
    with _UPSTREAM_LOCK:
        with _CACHE_LOCK:
            missing = list(dict.fromkeys(key for key in keys if key not in _CACHE))
        if missing:
            wait_seconds = 1.0 - (time.monotonic() - _LAST_UPSTREAM_REQUEST)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            query = urlencode({"latitude": ",".join(f"{key[1]:.5f}" for key in missing), "longitude": ",".join(f"{key[0]:.5f}" for key in missing)})
            request = Request(f"{API_URL}?{query}", headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            _LAST_UPSTREAM_REQUEST = time.monotonic()
            try:
                with urlopen(request, timeout=timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                values = payload.get("elevation")
                if not isinstance(values, list) or len(values) != len(missing):
                    raise ValueError("unexpected elevation response")
                parsed = [float(value) if value is not None else None for value in values]
            except (URLError, TimeoutError, OSError) as error:
                raise ElevationProviderError("ELEVATION_SERVICE_UNAVAILABLE", "公开高程服务暂不可用，请稍后重试或使用现有离线演示数据") from error
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                raise ElevationProviderError("INVALID_ELEVATION_RESPONSE", "公开高程服务返回数据格式异常") from error
            with _CACHE_LOCK:
                for key, value in zip(missing, parsed):
                    if value is not None and math.isfinite(value):
                        _CACHE[key] = (value, now_epoch, retrieved_at)
                while len(_CACHE) > CACHE_MAX_ENTRIES:
                    _CACHE.pop(next(iter(_CACHE)))

    with _CACHE_LOCK:
        samples = [{"longitude": point[0], "latitude": point[1], "elevation_m": _CACHE.get(key, (None, now_epoch, retrieved_at))[0]} for point, key in zip(normalized, keys)]
        timestamps = [_CACHE[key][2] for key in keys if key in _CACHE]
    return {
        "available": bool(samples) and all(item["elevation_m"] is not None for item in samples),
        "samples": samples,
        "sample_count": len(samples),
        "source": "Open-Meteo Elevation API",
        "source_url": "https://open-meteo.com/en/docs/elevation-api",
        "endpoint": API_URL,
        "retrieved_at": max(timestamps) if timestamps else retrieved_at,
        "coordinate_reference": "WGS84 / EPSG:4326 input",
        "vertical_datum": "未由接口响应声明；不得用于跨基准净空换算",
        "source_resolution_m": 90,
        "source_resolution_note": "Open-Meteo 官方文档标称 Copernicus DEM GLO-90 / 90m；本次响应未单独返回分辨率",
        "quality_level": "public_reference_only",
        "data_boundary": "公开参考地形高程；Copernicus DEM GLO-90 / 90m 标称分辨率，不含建筑/树木/线缆高度，不用于真实飞行安全放行；请署名 Copernicus DEM",
        "usage_terms": "须遵守 Open-Meteo 署名与使用条款；商业部署前需核验并取得对应商业许可",
    }
