"""Fetch a bounded OSM reference extract for the offline Liangping demo map."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "frontend" / "data" / "liangping-osm-reference.geojson"
BBOX = (107.70, 30.62, 107.82, 30.74)
API = "https://api.openstreetmap.org/api/0.6/map"
ALLOWED_TAGS = {"highway", "waterway", "landuse", "natural", "leisure"}


def main() -> None:
    query = urllib.parse.urlencode({"bbox": ",".join(map(str, BBOX))})
    request = urllib.request.Request(
        f"{API}?{query}",
        headers={
            "User-Agent": "LiangpingLowAltitudePlatform/0.6.1 (local demo map data preparation)",
            "Accept": "application/xml",
        },
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        root = ET.fromstring(response.read())

    nodes = {
        node.attrib["id"]: [float(node.attrib["lon"]), float(node.attrib["lat"])]
        for node in root.findall("node")
    }
    features = []
    for way in root.findall("way"):
        tags = {item.attrib["k"]: item.attrib["v"] for item in way.findall("tag")}
        if not ALLOWED_TAGS.intersection(tags):
            continue
        coordinates = [nodes[item.attrib["ref"]] for item in way.findall("nd") if item.attrib["ref"] in nodes]
        if len(coordinates) < 2:
            continue
        closed = len(coordinates) >= 4 and coordinates[0] == coordinates[-1]
        polygonal = any(key in tags for key in ("landuse", "leisure")) or tags.get("natural") == "water"
        if closed and polygonal:
            geometry_type, geometry_coordinates = "Polygon", [coordinates]
        else:
            geometry_type, geometry_coordinates = "LineString", coordinates

        if "highway" in tags:
            asset_type = "road"
        elif "waterway" in tags or tags.get("natural") == "water":
            asset_type = "water"
        else:
            asset_type = "landuse"
        features.append({
            "type": "Feature",
            "id": f"osm-way-{way.attrib['id']}",
            "properties": {
                "asset_type": asset_type,
                "class": tags.get("highway") or tags.get("waterway") or tags.get("landuse") or tags.get("natural") or tags.get("leisure"),
                "name": tags.get("name"),
                "source_kind": "openstreetmap_reference",
                "osm_way_id": way.attrib["id"],
            },
            "geometry": {"type": geometry_type, "coordinates": geometry_coordinates},
        })

    document = {
        "type": "FeatureCollection",
        "metadata": {
            "source": "OpenStreetMap API map extract",
            "source_url": API,
            "license": "Open Database License (ODbL) 1.0",
            "attribution": "© OpenStreetMap contributors",
            "coordinate_reference": "WGS84",
            "bbox": list(BBOX),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "feature_count": len(features),
            "data_boundary": "Public geographic reference only; not authoritative survey, airspace authorization, or flight-safety data.",
            "excluded": ["building collision data", "authorized airspace", "flight permits"],
        },
        "features": features,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"prepared OSM reference map: {len(features)} ways -> {OUTPUT}")


if __name__ == "__main__":
    main()
