"""Add reproducible synthetic reference and hazard points across the loaded map extent."""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_PATH = ROOT / "data" / "demo" / "spatial_assets.json"
OSM_PATH = ROOT / "frontend" / "data" / "liangping-osm-reference.geojson"
SEED = 20261017
REFERENCE_COUNT = 30
RISK_COUNT = 24


def point_feature(point_id: str, name: str, asset_type: str, longitude: float, latitude: float, **properties: object) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "point_id": point_id,
            "name": name,
            "asset_type": asset_type,
            "source_kind": "synthetic_demo",
            "quality_level": "synthetic_demo",
            "visible_default": True,
            "generated_for": "map_visualization_only",
            **properties,
        },
        "geometry": {"type": "Point", "coordinates": [round(longitude, 6), round(latitude, 6)]},
    }


def main() -> None:
    assets = json.loads(ASSET_PATH.read_text(encoding="utf-8"))
    osm = json.loads(OSM_PATH.read_text(encoding="utf-8"))
    min_lng, min_lat, max_lng, max_lat = map(float, osm["metadata"]["bbox"])
    rng = random.Random(SEED)
    features = [
        feature
        for feature in assets.get("features", [])
        if not str((feature.get("properties") or {}).get("point_id", "")).startswith(("SYN-REF-", "SYN-RISK-"))
    ]
    for index in range(1, REFERENCE_COUNT + 1):
        longitude = rng.uniform(min_lng + 0.002, max_lng - 0.002)
        latitude = rng.uniform(min_lat + 0.002, max_lat - 0.002)
        features.append(point_feature(
            f"SYN-REF-{index:03d}", f"合成参考点-{index:02d}", "route_reference_point", longitude, latitude,
            reference_kind="synthetic_navigation_reference", selectable_as_route_waypoint=True,
        ))
    for index in range(1, RISK_COUNT + 1):
        longitude = rng.uniform(min_lng + 0.002, max_lng - 0.002)
        latitude = rng.uniform(min_lat + 0.002, max_lat - 0.002)
        features.append(point_feature(
            f"SYN-RISK-{index:03d}", f"合成危险点-{index:02d}", "hazard", longitude, latitude,
            risk_level="high" if index % 6 == 0 else "medium", height_m=rng.randint(12, 96),
            risk_kind="synthetic_obstacle_reference", requires_human_verification=True,
        ))
    assets["features"] = features
    assets.setdefault("metadata", {})["synthetic_point_generation"] = {
        "seed": SEED,
        "reference_points": REFERENCE_COUNT,
        "hazard_points": RISK_COUNT,
        "distribution_bbox": [min_lng, min_lat, max_lng, max_lat],
        "distribution_source": "loaded OpenStreetMap reference extract extent; not an authoritative administrative boundary",
        "usage": "visualization-only synthetic points; do not use for flight authorization or safety decisions",
    }
    ASSET_PATH.write_text(json.dumps(assets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"generated {REFERENCE_COUNT} synthetic reference points and {RISK_COUNT} synthetic hazard points in {ASSET_PATH}")


if __name__ == "__main__":
    main()
