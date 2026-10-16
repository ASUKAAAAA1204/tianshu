"""准备梁平公开参考空间资产，供离线平台加载。

生成文件：data/demo/spatial_assets.json
数据来源：仓库已保存的 OSM 边界、公开设施/高程样本，以及 OSM 机场 way。
机场原始几何通过 OpenStreetMap API 获取；失败时保留仓库已有元数据，不伪造边界。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "材料包-梁平低空运行基础底座" / "sources" / "空间数据"
OUTPUT = ROOT / "data" / "demo" / "spatial_assets.json"
AIRPORT_WAY_ID = 455473647


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def airport_from_osm() -> dict | None:
    url = f"https://api.openstreetmap.org/api/0.6/way/{AIRPORT_WAY_ID}/full.json"
    request = Request(url, headers={"User-Agent": "LiangpingLowAltitudeResearch/0.1"})
    try:
        payload = json.loads(urlopen(request, timeout=30).read().decode("utf-8"))
    except Exception:
        return None
    nodes = {item["id"]: [item["lon"], item["lat"]] for item in payload.get("elements", []) if item.get("type") == "node"}
    way = next((item for item in payload.get("elements", []) if item.get("type") == "way" and item.get("id") == AIRPORT_WAY_ID), None)
    if not way or not way.get("nodes") or any(node_id not in nodes for node_id in way["nodes"]):
        return None
    tags = way.get("tags", {})
    return {
        "type": "Feature",
        "properties": {
            "name": tags.get("name", "重庆梁平机场"),
            "asset_type": "airport_reference",
            "layer_type": "restricted",
            "level": "soft",
            "source": "OpenStreetMap",
            "source_id": f"way/{AIRPORT_WAY_ID}",
            "quality_level": "public_reference",
            "rule_enabled": False,
            "usage": "公开机场范围参考，不等同于净空保护区",
        },
        "geometry": {"type": "Polygon", "coordinates": [[nodes[node_id] for node_id in way["nodes"]]]},
    }


def main() -> None:
    features = []
    boundary = read_json(SOURCE / "liangping_boundary_osm.geojson")
    boundary["properties"] = {
        **boundary.get("properties", {}),
        "asset_type": "administrative_boundary",
        "layer_type": "operable",
        "level": "open",
        "quality_level": "public_reference",
        "usage": "梁平行政范围参考",
    }
    features.append(boundary)

    airport = airport_from_osm()
    if airport:
        features.append(airport)

    with (SOURCE / "liangping_demo_facilities_points.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            features.append({
                "type": "Feature",
                "properties": {
                    "name": row["name"],
                    "asset_type": "facility_point",
                    "facility_type": row["type"],
                    "point_id": row["point_id"],
                    "altitude_m": float(row["altitude_m"]),
                    "status": row["status"],
                    "source": row["source_label"],
                    "quality_level": "synthetic_demo",
                    "usage": row["usage"],
                },
                "geometry": {"type": "Point", "coordinates": [float(row["longitude"]), float(row["latitude"])]},
            })

    with (SOURCE / "liangping_elevation_sample.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            features.append({
                "type": "Feature",
                "properties": {
                    "name": row["point_id"],
                    "asset_type": "elevation_sample",
                    "elevation_m": float(row["elevation_m"]),
                    "source": row["source"],
                    "quality_level": "regional_sample",
                    "usage": "区域高程参考，不替代精细 DEM",
                },
                "geometry": {"type": "Point", "coordinates": [float(row["longitude"]), float(row["latitude"])]},
            })

    OUTPUT.write_text(json.dumps({
        "type": "FeatureCollection",
        "metadata": {
            "name": "梁平公开参考空间资产",
            "generated_at": "2026-09-18",
            "offline_ready": True,
            "source_policy": "公开参考与合成演示数据分层标识，不作为权威空域规则",
        },
        "features": features,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUTPUT} with {len(features)} features")


if __name__ == "__main__":
    main()
