"""Validate the non-3D public API surface against the running demo service."""
from __future__ import annotations

import json
import os
import urllib.request

BASE = os.environ.get("LP_BASE_URL", "http://127.0.0.1:8765")


def call(path: str, token: str):
    request = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=8) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def main() -> None:
    login = urllib.request.Request(
        f"{BASE}/api/auth/login",
        data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(login, timeout=8) as response:
        token = json.loads(response.read().decode())["token"]
    status, bootstrap = call("/api/bootstrap", token)
    required = {"missions", "vehicles", "layers", "rules", "spatial_assets", "map_features", "traceability", "airspace_cells", "facilities"}
    if status != 200 or not required.issubset(bootstrap):
        raise AssertionError(f"bootstrap surface incomplete: {sorted(required - set(bootstrap))}")
    if not bootstrap["airspace_cells"] or not bootstrap["facilities"] or not bootstrap["traceability"].get("engine_version"):
        raise AssertionError("spatial or traceability payload empty")
    status, features = call("/api/map/features", token)
    if status != 200 or features.get("type") != "FeatureCollection" or not features.get("features"):
        raise AssertionError("map feature endpoint invalid")
    print(json.dumps({"status": "passed", "bootstrap_keys": len(bootstrap), "airspace_cells": len(bootstrap["airspace_cells"]), "facilities": len(bootstrap["facilities"]), "map_features": len(features["features"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
