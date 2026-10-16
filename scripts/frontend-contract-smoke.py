"""Offline frontend contract smoke test for the Liangping demo runtime."""
from __future__ import annotations

import json
import os
import urllib.request


BASE = os.environ.get("LP_BASE_URL", "http://127.0.0.1:8765")


def request(path: str, method: str = "GET", body: dict | None = None, token: str | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=8) as response:
        return response.status, response.read().decode("utf-8")


def main() -> None:
    _, html = request("/")
    required = [
        'id="mapCanvas"', 'id="mapZoomIn"', 'id="mapZoomOut"',
        'id="mapReset"', 'id="altitudeFilter"', 'id="altitudeLayerReadout"',
        'id="layerList"', 'id="facilityList"', '公开参考 / 合成演示数据',
        'id="dataRegister"',
        '/vendor/maplibre-gl.js', '/adapters/maplibre-adapter.js',
    ]
    missing = [item for item in required if item not in html]
    if missing:
        raise AssertionError(f"frontend contract missing: {missing}")
    for asset in ("/styles.css", "/app.js", "/map-controller.js", "/adapters/map-adapter.js", "/adapters/maplibre-adapter.js", "/vendor/maplibre-gl.js", "/data/liangping-osm-reference.geojson"):
        status, _ = request(asset)
        if status != 200:
            raise AssertionError(f"asset unavailable: {asset} status={status}")
    _, adapter_source = request("/adapters/maplibre-adapter.js")
    if '"lp-geography"' not in adapter_source or '"lp-reference-roads"' not in adapter_source or "map-attribution" not in adapter_source:
        raise AssertionError("MapLibre local reference geography or visible attribution contract missing")
    _, geography_payload = request("/data/liangping-osm-reference.geojson")
    geography = json.loads(geography_payload)
    if geography.get("type") != "FeatureCollection" or len(geography.get("features", [])) < 100 or geography.get("metadata", {}).get("license") != "Open Database License (ODbL) 1.0":
        raise AssertionError("local OSM reference dataset contract incomplete")
    status, payload = request("/api/auth/login", "POST", {"username": "admin", "password": "admin123"})
    if status != 200:
        raise AssertionError("admin login failed")
    token = json.loads(payload)["token"]
    status, payload = request("/api/bootstrap", token=token)
    bootstrap = json.loads(payload)
    if status != 200 or not bootstrap.get("missions") or not bootstrap.get("vehicles"):
        raise AssertionError("bootstrap contract incomplete")
    status, payload = request("/api/map/features", token=token)
    features = json.loads(payload)
    if status != 200 or features.get("type") != "FeatureCollection" or not features.get("features"):
        raise AssertionError("map feature contract incomplete")
    print(json.dumps({"status": "passed", "assets": 5, "missions": len(bootstrap["missions"]), "map_features": len(features["features"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
