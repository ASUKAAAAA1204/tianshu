"""Verify that open-source components claimed as embedded are actually present."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def require(condition, message):
    if not condition:
        raise AssertionError(message)

def main():
    index = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    adapter = (ROOT / "frontend/adapters/maplibre-adapter.js").read_text(encoding="utf-8")
    vendor = (ROOT / "frontend/vendor/maplibre-gl.js").read_text(encoding="utf-8", errors="ignore")
    require((ROOT / "frontend/vendor/maplibre-gl.js").is_file(), "MapLibre JS vendor missing")
    require((ROOT / "frontend/vendor/maplibre-gl.css").is_file(), "MapLibre CSS vendor missing")
    require("/vendor/maplibre-gl.js" in index and "/vendor/maplibre-gl.css" in index, "MapLibre entry not referenced")
    require("module.Map" in adapter and "maplibregl.Marker" in adapter, "MapLibre runtime API not used")
    require("MapLibre GL JS" in vendor and "3-Clause BSD" in vendor, "MapLibre version/license marker missing")
    compose = (ROOT / "docker-compose.postgres.yml").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements-postgres.txt").read_text(encoding="utf-8")
    require("postgis/postgis:16-3.4" in compose, "PostGIS image pin missing")
    require("psycopg" in requirements, "psycopg dependency declaration missing")
    require(not re.search(r"(?:cesium|leaflet|openlayers|three(?:\.js)?|@turf)", index + adapter, re.I), "excluded engine accidentally embedded")
    print("OSS embedding smoke passed: MapLibre=embedded, PostGIS/psycopg=declared, Cesium=out-of-scope")

if __name__ == "__main__":
    main()
