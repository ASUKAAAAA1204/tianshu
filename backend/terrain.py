"""离线 DEM 读取与航线地形指标计算。"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEM_GRID = ROOT / "data" / "demo" / "liangping_dem_grid.json"


@lru_cache(maxsize=1)
def load_grid() -> dict:
    if not DEM_GRID.exists():
        return {}
    return json.loads(DEM_GRID.read_text(encoding="utf-8"))


def sample_elevation(lng: float, lat: float) -> float | None:
    grid = load_grid()
    lats, lngs, rows = grid.get("latitudes", []), grid.get("longitudes", []), grid.get("elevations_m", [])
    if not lats or not lngs or not rows:
        return None
    row = min(range(len(lats)), key=lambda idx: abs(lats[idx] - lat))
    col = min(range(len(lngs)), key=lambda idx: abs(lngs[idx] - lng))
    value = rows[row][col]
    return float(value) if value is not None else None


def route_terrain_metrics(points: list[list[float]], planned_altitude: float) -> dict:
    samples: list[float] = []
    for left, right in zip(points, points[1:]):
        distance_m = _distance_m(left[0], left[1], right[0], right[1])
        steps = max(1, math.ceil(distance_m / 400))
        for idx in range(steps):
            ratio = idx / steps
            elevation = sample_elevation(left[0] + (right[0] - left[0]) * ratio, left[1] + (right[1] - left[1]) * ratio)
            if elevation is not None:
                samples.append(elevation)
    if points:
        elevation = sample_elevation(points[-1][0], points[-1][1])
        if elevation is not None:
            samples.append(elevation)
    if not samples:
        return {"available": False, "sample_count": 0, "terrain_risk": "unknown"}
    start_elevation = samples[0]
    terrain_max = max(samples)
    relief = max(0.0, terrain_max - start_elevation)
    clearance = float(planned_altitude) - relief
    risk = "high" if clearance < 30 else ("medium" if clearance < 80 else "low")
    return {"available": True, "sample_count": len(samples), "start_elevation_m": round(start_elevation, 1), "terrain_max_m": round(terrain_max, 1), "terrain_relief_m": round(relief, 1), "clearance_min_m": round(clearance, 1), "terrain_risk": risk, "thresholds": {"high_below_m": 30, "medium_below_m": 80}}


def _distance_m(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    radius = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))
