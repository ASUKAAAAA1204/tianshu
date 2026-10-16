"""统一地图要素输出，屏蔽离线静态资产与运行图层差异。"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def _static_features(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    result = []
    for index, feature in enumerate(payload.get("features", []) if isinstance(payload, dict) else []):
        if not isinstance(feature, dict) or not feature.get("geometry"):
            continue
        item = dict(feature); item["properties"] = {"source_kind": "public_reference", **(item.get("properties") or {})}; item.setdefault("id", f"asset-{index + 1}"); result.append(item)
    return result

def build_map_feature_collection(db: Any, static_assets_path: Path) -> dict[str, Any]:
    features = _static_features(static_assets_path); skipped = 0
    rows = db.execute("SELECT id,name,layer_type,level,version,status,source,geometry_json FROM layers WHERE status='published' ORDER BY id").fetchall()
    for row in rows:
        values = dict(row) if hasattr(row, "keys") else dict(zip(("id","name","layer_type","level","version","status","source","geometry_json"), row))
        try: geometry = json.loads(values["geometry_json"])
        except (TypeError, json.JSONDecodeError): skipped += 1; continue
        if not isinstance(geometry, dict) or not geometry.get("type"): skipped += 1; continue
        features.append({"type":"Feature","id":f"layer-{values['id']}","properties":{"name":values["name"],"layer_id":values["id"],"layer_type":values["layer_type"],"level":values["level"],"version":values["version"],"status":values["status"],"source":values["source"],"source_kind":"operational_layer","visible_default":True},"geometry":geometry})
    return {"type":"FeatureCollection","metadata":{"contract_version":"1.0","coordinate_reference":"EPSG:4326","generated_at":datetime.now(timezone.utc).isoformat(),"feature_count":len(features),"operational_layer_count":len(rows)-skipped,"skipped_layer_count":skipped},"features":features}
