"""Validate demo/reference data structure and optionally write a SHA-256 manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "demo"
DATA_FILES = (
    "data/demo/airspace_cells.json",
    "data/demo/facilities.json",
    "data/demo/layers.json",
    "data/demo/liangping_dem_grid.json",
    "data/demo/missions.json",
    "data/demo/rules.json",
    "data/demo/spatial_assets.json",
    "data/demo/vehicles.json",
    "frontend/data/liangping-osm-reference.geojson",
)
MANIFEST = ROOT / "data" / "spatial-data.sha256"
LON_RANGE = (-180.0, 180.0)
LAT_RANGE = (-90.0, 90.0)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def number(value: Any, label: str) -> float:
    require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{label}: expected number")
    result = float(value)
    require(math.isfinite(result), f"{label}: expected finite number")
    return result


def coordinate_pairs(value: Any, label: str) -> Iterable[tuple[float, float]]:
    require(isinstance(value, list), f"{label}: coordinates must be arrays")
    if len(value) >= 2 and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
        require(len(value) == 2, f"{label}: coordinates must be 2D [longitude, latitude]")
        lon = number(value[0], label)
        lat = number(value[1], label)
        require(LON_RANGE[0] <= lon <= LON_RANGE[1], f"{label}: longitude out of WGS84 range")
        require(LAT_RANGE[0] <= lat <= LAT_RANGE[1], f"{label}: latitude out of WGS84 range")
        yield lon, lat
        return
    require(bool(value), f"{label}: empty coordinate array")
    for child in value:
        yield from coordinate_pairs(child, label)


def validate_ring(ring: Any, label: str) -> None:
    points = list(coordinate_pairs(ring, label))
    require(len(points) >= 4, f"{label}: polygon ring requires at least four positions")
    require(points[0] == points[-1], f"{label}: polygon ring must be closed")
    area2 = sum(points[i][0] * points[i + 1][1] - points[i + 1][0] * points[i][1] for i in range(len(points) - 1))
    require(abs(area2) > 1e-12, f"{label}: polygon ring has zero area")


def validate_geometry(geometry: Any, label: str) -> int:
    require(isinstance(geometry, dict), f"{label}: missing geometry")
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    require(geometry_type in {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"}, f"{label}: unsupported geometry type {geometry_type!r}")
    pairs = list(coordinate_pairs(coordinates, label))
    if geometry_type == "Point":
        require(len(pairs) == 1, f"{label}: Point must have one position")
    elif geometry_type == "MultiPoint":
        require(len(coordinates) >= 1, f"{label}: MultiPoint must not be empty")
    elif geometry_type == "LineString":
        require(len(pairs) >= 2, f"{label}: LineString requires at least two positions")
    elif geometry_type == "MultiLineString":
        require(all(len(line) >= 2 for line in coordinates), f"{label}: each MultiLineString part requires at least two positions")
    elif geometry_type == "Polygon":
        require(bool(coordinates), f"{label}: Polygon must have at least one ring")
        for ring in coordinates:
            validate_ring(ring, label)
    elif geometry_type == "MultiPolygon":
        require(bool(coordinates), f"{label}: MultiPolygon must not be empty")
        for polygon in coordinates:
            require(bool(polygon), f"{label}: MultiPolygon member must have at least one ring")
            for ring in polygon:
                validate_ring(ring, label)
    return len(pairs)


def parse_time(value: Any, label: str) -> datetime | None:
    if value is None:
        return None
    require(isinstance(value, str) and bool(value.strip()), f"{label}: time must be ISO-8601 or null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label}: invalid ISO-8601 time") from error
    require(parsed.tzinfo is not None, f"{label}: time must include a UTC offset")
    return parsed


def load_json(relative_path: str) -> Any:
    path = ROOT / relative_path
    require(path.is_file(), f"required data file missing: {relative_path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid UTF-8 JSON: {relative_path}") from error


def validate_feature_collection(relative_path: str, value: Any, *, expected_source: str | None = None) -> tuple[int, int]:
    require(isinstance(value, dict) and value.get("type") == "FeatureCollection", f"{relative_path}: expected FeatureCollection")
    features = value.get("features")
    require(isinstance(features, list), f"{relative_path}: features must be an array")
    properties = 0
    coordinates = 0
    seen_ids: set[str] = set()
    for index, feature in enumerate(features):
        label = f"{relative_path} feature[{index}]"
        require(isinstance(feature, dict) and feature.get("type") == "Feature", f"{label}: expected Feature")
        props = feature.get("properties")
        require(isinstance(props, dict), f"{label}: properties must be an object")
        identifier = feature.get("id") or props.get("id") or props.get("point_id")
        if identifier is not None:
            key = str(identifier)
            require(key not in seen_ids, f"{label}: duplicate feature id {key}")
            seen_ids.add(key)
        if expected_source:
            require(props.get("source_kind") == expected_source, f"{label}: expected source_kind={expected_source}")
        coordinates += validate_geometry(feature.get("geometry"), label)
        properties += len(props)
    return len(features), coordinates


def validate_demo_data() -> dict[str, Any]:
    assets = load_json("data/demo/spatial_assets.json")
    metadata = assets.get("metadata") or {}
    require(metadata.get("source_policy") == "公开参考 / 合成演示数据", "spatial_assets: missing demo/reference source policy")
    require(metadata.get("coordinate_reference") == "WGS84", "spatial_assets: coordinate_reference must be WGS84")
    require(bool(metadata.get("data_boundary")), "spatial_assets: missing data boundary")
    asset_count, asset_coordinates = validate_feature_collection("data/demo/spatial_assets.json", assets, expected_source="synthetic_demo")
    reference_points = [feature for feature in assets["features"] if feature.get("properties", {}).get("asset_type") == "route_reference_point"]
    synthetic_risks = [feature for feature in assets["features"] if feature.get("properties", {}).get("point_id", "").startswith("SYN-RISK-")]
    require(len(reference_points) >= 30, "spatial_assets: expected at least 30 synthetic route reference points")
    require(len(synthetic_risks) >= 24, "spatial_assets: expected at least 24 synthetic risk points")

    osm = load_json("frontend/data/liangping-osm-reference.geojson")
    osm_metadata = osm.get("metadata") or {}
    require(osm_metadata.get("source_url") == "https://api.openstreetmap.org/api/0.6/map", "OSM reference: unexpected source URL")
    require(osm_metadata.get("license") == "Open Database License (ODbL) 1.0", "OSM reference: missing ODbL license")
    require(osm_metadata.get("attribution") == "© OpenStreetMap contributors", "OSM reference: missing attribution")
    require(osm_metadata.get("coordinate_reference") == "WGS84", "OSM reference: coordinate_reference must be WGS84")
    require(bool(osm_metadata.get("data_boundary")), "OSM reference: missing data boundary")
    require({"building collision data", "authorized airspace", "flight permits"}.issubset(set(osm_metadata.get("excluded", []))), "OSM reference: missing excluded-capability boundaries")
    bbox = osm_metadata.get("bbox")
    require(isinstance(bbox, list) and len(bbox) == 4, "OSM reference: bbox must contain four coordinates")
    west, south, east, north = (number(item, "OSM reference bbox") for item in bbox)
    require(west < east and south < north, "OSM reference: invalid bbox ordering")
    retrieved_at = parse_time(osm_metadata.get("retrieved_at"), "OSM reference retrieved_at")
    require(retrieved_at is not None, "OSM reference: retrieved_at is required")
    osm_count, osm_coordinates = validate_feature_collection("frontend/data/liangping-osm-reference.geojson", osm, expected_source="openstreetmap_reference")
    require(osm_count == osm_metadata.get("feature_count"), "OSM reference: metadata feature_count mismatch")
    require(all(feature.get("properties", {}).get("asset_type") in {"road", "water", "landuse"} for feature in osm["features"]), "OSM reference: unexpected feature class")

    grid = load_json("data/demo/liangping_dem_grid.json")
    grid_metadata = grid.get("metadata") or {}
    require(grid_metadata.get("source") == "synthetic_demo", "DEM grid must remain marked synthetic_demo")
    require(grid_metadata.get("coordinate_reference", "WGS84") == "WGS84", "DEM grid must use WGS84 coordinates")
    lats, lngs, elevations = grid.get("latitudes"), grid.get("longitudes"), grid.get("elevations_m")
    require(isinstance(lats, list) and lats and isinstance(lngs, list) and lngs, "DEM grid axes are missing")
    require(len(lats) == len(elevations) and all(isinstance(row, list) and len(row) == len(lngs) for row in elevations), "DEM grid dimensions do not match axes")
    for axis_name, axis, bounds in (("latitude", lats, LAT_RANGE), ("longitude", lngs, LON_RANGE)):
        values = [number(item, f"DEM {axis_name}") for item in axis]
        require(all(bounds[0] <= item <= bounds[1] for item in values), f"DEM {axis_name} outside WGS84 range")
        require(len(set(values)) == len(values), f"DEM {axis_name} axis has duplicate values")
    elevation_values = [number(item, "DEM elevation") for row in elevations for item in row]
    require(all(-500 <= item <= 9000 for item in elevation_values), "DEM elevation outside configured plausibility range")
    bbox_meta = grid_metadata.get("bbox") or {}
    require(min(map(float, lats)) == float(bbox_meta["min_lat"]) and max(map(float, lats)) == float(bbox_meta["max_lat"]), "DEM latitude bounds mismatch metadata")
    require(min(map(float, lngs)) == float(bbox_meta["min_lng"]) and max(map(float, lngs)) == float(bbox_meta["max_lng"]), "DEM longitude bounds mismatch metadata")

    cells = load_json("data/demo/airspace_cells.json")
    require(isinstance(cells, list) and bool(cells), "airspace cells must be a non-empty array")
    cell_ids: set[str] = set()
    for index, cell in enumerate(cells):
        label = f"airspace_cells[{index}]"
        cell_id = str(cell.get("cell_id", ""))
        require(cell_id and cell_id not in cell_ids, f"{label}: missing or duplicate cell_id")
        cell_ids.add(cell_id)
        require(cell.get("source_kind") == "synthetic_demo", f"{label}: missing synthetic source marker")
        minimum = number(cell.get("min_altitude_m"), f"{label} min_altitude_m")
        maximum = number(cell.get("max_altitude_m"), f"{label} max_altitude_m")
        require(0 <= minimum <= maximum, f"{label}: invalid altitude interval")
        validate_geometry(cell.get("geometry"), label)
        starts = parse_time(cell.get("valid_from"), f"{label} valid_from")
        ends = parse_time(cell.get("valid_to"), f"{label} valid_to")
        require(starts is None or ends is None or starts <= ends, f"{label}: invalid validity interval")

    facilities = load_json("data/demo/facilities.json")
    require(isinstance(facilities, list) and bool(facilities), "facilities must be a non-empty array")
    facility_ids: set[str] = set()
    for index, item in enumerate(facilities):
        label = f"facilities[{index}]"
        identifier = str(item.get("facility_id", ""))
        require(identifier and identifier not in facility_ids, f"{label}: missing or duplicate facility_id")
        facility_ids.add(identifier)
        require(item.get("source_kind") == "synthetic_demo", f"{label}: missing synthetic source marker")
        lon = number(item.get("longitude"), f"{label} longitude")
        lat = number(item.get("latitude"), f"{label} latitude")
        require(105 <= lon <= 110 and 28 <= lat <= 32, f"{label}: outside configured Liangping review bounds")
        number(item.get("elevation_m"), f"{label} elevation_m")
        require(number(item.get("service_radius_m"), f"{label} service_radius_m") > 0, f"{label}: service radius must be positive")
        require(item.get("status") in {"active", "inactive"}, f"{label}: unexpected facility status")
        require(bool(item.get("data_version")), f"{label}: missing data_version")

    other_features = 0
    other_coordinates = 0
    for relative_path in ("data/demo/layers.json",):
        feature_count, coordinate_count = validate_feature_collection(relative_path, load_json(relative_path))
        other_features += feature_count
        other_coordinates += coordinate_count
    for relative_path in ("data/demo/missions.json", "data/demo/rules.json", "data/demo/vehicles.json"):
        value = load_json(relative_path)
        require(isinstance(value, list), f"{relative_path}: expected array")
        if relative_path.endswith("missions.json"):
            for index, mission in enumerate(value):
                label = f"{relative_path}[{index}]"
                for field in ("start_lng", "start_lat", "end_lng", "end_lat"):
                    number(mission.get(field), f"{label} {field}")
                for prefix in ("start", "end"):
                    lon = number(mission[f"{prefix}_lng"], f"{label} {prefix}_lng")
                    lat = number(mission[f"{prefix}_lat"], f"{label} {prefix}_lat")
                    require(105 <= lon <= 110 and 28 <= lat <= 32, f"{label}: {prefix} coordinate outside Liangping review bounds")
        elif relative_path.endswith("vehicles.json"):
            for index, vehicle in enumerate(value):
                label = f"{relative_path}[{index}]"
                lon, lat = number(vehicle.get("longitude"), f"{label} longitude"), number(vehicle.get("latitude"), f"{label} latitude")
                require(105 <= lon <= 110 and 28 <= lat <= 32, f"{label}: coordinate outside Liangping review bounds")
                require(0 <= number(vehicle.get("battery"), f"{label} battery") <= 100, f"{label}: battery outside 0..100")
        other_features += len(value)

    return {
        "spatial_assets": asset_count,
        "synthetic_reference_points": len(reference_points),
        "synthetic_risk_points": len(synthetic_risks),
        "spatial_asset_coordinates": asset_coordinates,
        "airspace_cells": len(cells),
        "facilities": len(facilities),
        "dem_grid": f"{len(lats)}x{len(lngs)}",
        "dem_elevation_samples": len(elevation_values),
        "osm_reference_features": osm_count,
        "osm_reference_coordinates": osm_coordinates,
        "other_demo_records": other_features,
        "other_demo_coordinates": other_coordinates,
        "topology_validation": "not performed (Shapely unavailable)",
        "missing_optional_sources": [
            path for path in ("data/source/dem/N30E107.hgt.gz", "data/source/dem/N30E108.hgt.gz")
            if not (ROOT / path).is_file()
        ],
        "readiness_boundary": "demo/reference data only; synthetic DEM; no authoritative airspace or building collision dataset",
    }


def current_manifest_entries() -> list[str]:
    entries = []
    for relative_path in DATA_FILES:
        path = ROOT / relative_path
        require(path.is_file(), f"cannot hash missing data file: {relative_path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append(f"{digest}  {relative_path}")
    return entries


def write_manifest() -> int:
    entries = current_manifest_entries()
    MANIFEST.write_text("\n".join(entries) + "\n", encoding="ascii")
    return len(entries)


def verify_manifest() -> int:
    require(MANIFEST.is_file(), f"SHA-256 manifest missing: {MANIFEST.relative_to(ROOT).as_posix()}")
    expected = current_manifest_entries()
    actual = MANIFEST.read_text(encoding="ascii").splitlines()
    require(actual == expected, "SHA-256 manifest mismatch; data changed or manifest is stale")
    return len(actual)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--write-manifest", action="store_true", help="write deterministic SHA-256 manifest for demo/reference data")
    actions.add_argument("--check-manifest", action="store_true", help="verify data files against the existing SHA-256 manifest")
    args = parser.parse_args()
    result = validate_demo_data()
    if args.write_manifest:
        result["sha256_manifest"] = {"path": MANIFEST.relative_to(ROOT).as_posix(), "entries": write_manifest()}
    elif args.check_manifest:
        result["sha256_manifest"] = {"path": MANIFEST.relative_to(ROOT).as_posix(), "entries_verified": verify_manifest()}
    print(json.dumps({"status": "passed", "checks": result}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"demo data validation failed: {error}") from error
