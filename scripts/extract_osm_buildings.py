"""Extract a bounded OSM building sample from a Geofabrik GeoPackage using stdlib only.

The parser intentionally supports the MULTIPOLYGON geometry emitted by the
Geofabrik free export and retains source tags without inventing heights.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import struct
from pathlib import Path


def _wkb(data: bytes, offset: int = 0):
    endian = "<" if data[offset] == 1 else ">"
    offset += 1
    geometry_type = struct.unpack_from(endian + "I", data, offset)[0]
    offset += 4
    if geometry_type >= 1000:
        geometry_type %= 1000
        offset += 3 * 8
    if geometry_type != 6:
        raise ValueError(f"unsupported WKB geometry type {geometry_type}")
    polygon_count = struct.unpack_from(endian + "I", data, offset)[0]
    offset += 4
    polygons = []
    for _ in range(polygon_count):
        # Each polygon in a collection carries its own endian/type header.
        polygon_endian = "<" if data[offset] == 1 else ">"
        offset += 1
        polygon_type = struct.unpack_from(polygon_endian + "I", data, offset)[0]
        offset += 4
        if polygon_type >= 1000:
            polygon_type %= 1000
            offset += 3 * 8
        if polygon_type != 3:
            raise ValueError(f"unsupported polygon geometry type {polygon_type}")
        ring_count = struct.unpack_from(polygon_endian + "I", data, offset)[0]
        offset += 4
        rings = []
        for _ in range(ring_count):
            point_count = struct.unpack_from(polygon_endian + "I", data, offset)[0]
            offset += 4
            ring = []
            for _ in range(point_count):
                x, y = struct.unpack_from(polygon_endian + "dd", data, offset)
                offset += 16
                ring.append([x, y])
            rings.append(ring)
        polygons.append(rings)
    return {"type": "MultiPolygon", "coordinates": [[ring for ring in polygon] for polygon in polygons]}


def _geometry(blob: bytes):
    if blob[:2] != b"GP":
        raise ValueError("missing GeoPackage geometry header")
    flags = blob[3]
    envelope = (flags >> 1) & 7
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    return _wkb(blob[8 + envelope_sizes[envelope]:])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("gpkg", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--min-lng", type=float, default=107.70)
    parser.add_argument("--min-lat", type=float, default=30.62)
    parser.add_argument("--max-lng", type=float, default=107.82)
    parser.add_argument("--max-lat", type=float, default=30.74)
    args = parser.parse_args()
    conn = sqlite3.connect(args.gpkg)
    rows = conn.execute("SELECT fid, geom, osm_id, name, type FROM gis_osm_buildings_a_free")
    features = []
    scanned = 0
    for fid, blob, osm_id, name, kind in rows:
        scanned += 1
        if not blob or len(blob) < 40:
            continue
        # GeoPackage XY envelope is available in the header for this export.
        flags = blob[3]
        envelope = (flags >> 1) & 7
        if envelope not in (1, 2, 3, 4):
            continue
        min_x, max_x, min_y, max_y = struct.unpack_from("<dddd", blob, 8)
        if max_x < args.min_lng or min_x > args.max_lng or max_y < args.min_lat or min_y > args.max_lat:
            continue
        geometry = _geometry(blob)
        features.append({"type": "Feature", "id": str(osm_id or fid), "properties": {"name": name or None, "building": kind or "building", "height": None, "height_source": "not_provided", "source": "Geofabrik / OpenStreetMap", "source_license": "ODbL-1.0", "source_timestamp": "2026-10-18T20:25:06Z"}, "geometry": geometry})
    payload = {"type": "FeatureCollection", "metadata": {"source": "Geofabrik Chongqing OSM extract", "source_url": "https://download.geofabrik.de/asia/china/chongqing-latest-free.gpkg.zip", "license": "ODbL-1.0", "acquired_at": "2026-10-18T20:25:06Z", "coordinate_reference": "EPSG:4326", "bbox": [args.min_lng, args.min_lat, args.max_lng, args.max_lat], "scanned_features": scanned, "building_features": len(features), "height_policy": "missing height remains null; no estimated height"}, "features": features}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"scanned": scanned, "buildings": len(features), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
