from __future__ import annotations

import json
import html
import mimetypes
import csv
import io
import os
import re
import sqlite3
import math
import hashlib
import secrets
import time
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from db import database_capabilities, database_config, hash_password, init_db, rows, session, verify_password
from geometry import segment_intersects_polygon, segments_intersect
from terrain import route_terrain_metrics
from repository import build_storage
from telemetry import TelemetryError, normalize_telemetry, runtime_alerts
from map_adapter import build_map_feature_collection
from versioning import ENGINE_VERSION, traceability


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
SPATIAL_ASSETS = ROOT / "data" / "demo" / "spatial_assets.json"
DEM_GRID = ROOT / "data" / "demo" / "liangping_dem_grid.json"
SPATIAL_ASSETS = ROOT / "data" / "demo" / "spatial_assets.json"
DEM_GRID = ROOT / "data" / "demo" / "liangping_dem_grid.json"
MISSION_ID = re.compile(r"^[A-Z0-9-]{4,40}$")
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"
PRODUCTION_MODE = os.environ.get("LP_ENV", "development").lower() == "production"
MAP_STYLE_URL = os.environ.get("LP_MAP_STYLE_URL", "").strip()
MAX_BODY_BYTES = int(os.environ.get("LP_MAX_BODY_BYTES", "2097152"))
SESSION_TTL_SECONDS = int(os.environ.get("LP_SESSION_TTL_SECONDS", "28800"))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("LP_RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_MAX_REQUESTS = int(os.environ.get("LP_RATE_LIMIT_MAX_REQUESTS", "120"))
STARTED_AT = time.time()
RATE_BUCKETS = {}
RATE_LOCK = threading.Lock()


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def parse_optional_time(value, field_name):
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ApiError(422, "INVALID_TIME_WINDOW", f"{field_name} 必须是 ISO-8601 时间") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def normalize_time_window(payload):
    start = parse_optional_time(payload.get("time_window_start"), "time_window_start")
    end = parse_optional_time(payload.get("time_window_end"), "time_window_end")
    if (start is None) != (end is None):
        raise ApiError(422, "INCOMPLETE_TIME_WINDOW", "时间窗口必须同时提供开始和结束时间")
    if start and end and datetime.fromisoformat(start) >= datetime.fromisoformat(end):
        raise ApiError(422, "INVALID_TIME_WINDOW", "时间窗口结束时间必须晚于开始时间")
    return start, end


def windows_overlap(left_start, left_end, right_start, right_end):
    if not all((left_start, left_end, right_start, right_end)):
        return False
    return datetime.fromisoformat(left_start) < datetime.fromisoformat(right_end) and datetime.fromisoformat(right_start) < datetime.fromisoformat(left_end)


def route_paths_intersect(left_points, right_points):
    if len(left_points) < 2 or len(right_points) < 2:
        return False
    for left_a, left_b in zip(left_points, left_points[1:]):
        for right_a, right_b in zip(right_points, right_points[1:]):
            if segments_intersect(tuple(left_a[:2]), tuple(left_b[:2]), tuple(right_a[:2]), tuple(right_b[:2])):
                return True
    return False


def insert_returning_id(db, query, params=()):
    cursor = db.execute(query.rstrip().rstrip(";") + " RETURNING id", params)
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("INSERT 未返回主键")
    return row["id"] if isinstance(row, dict) else row[0]


def telemetry_track_csv(samples):
    """Serialize an ordered flight track with spreadsheet formula injection guards."""
    fields = (
        "sequence", "timestamp", "longitude", "latitude", "altitude", "speed",
        "heading", "battery", "link_quality", "status", "source",
    )
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(fields)
    for sample in samples:
        values = []
        for field in fields:
            value = sample.get(field, "")
            if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return "\ufeff" + output.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "LiangpingLowAltitude/0.2"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def _security_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        if PRODUCTION_MODE:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    def _json(self, payload, status=HTTPStatus.OK, extra_headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._security_headers()
        for key, value in (extra_headers or {}).items():
            self.send_header(key, str(value))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, body: str, content_type: str, status=HTTPStatus.OK, extra_headers=None):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self._security_headers()
        for key, value in (extra_headers or {}).items():
            self.send_header(key, str(value))
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _error(self, error: ApiError):
        headers = {}
        if error.status == HTTPStatus.TOO_MANY_REQUESTS:
            headers = {"Retry-After": "1", "X-RateLimit-Limit": str(RATE_LIMIT_MAX_REQUESTS)}
        self._json({"code": error.code, "message": error.message}, error.status, headers)

    def _body(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > MAX_BODY_BYTES:
                raise ApiError(413, "BODY_TOO_LARGE", "请求体超过允许大小")
            return json.loads(self.rfile.read(size).decode("utf-8"))
        except ApiError:
            raise
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, "INVALID_JSON", "请求体必须是有效的 JSON")

    def _rate_limit(self):
        now = time.time()
        key = (self.client_address[0], urlparse(self.path).path)
        with RATE_LOCK:
            bucket = [item for item in RATE_BUCKETS.get(key, []) if now - item < RATE_LIMIT_WINDOW_SECONDS]
            if len(bucket) >= RATE_LIMIT_MAX_REQUESTS:
                RATE_BUCKETS[key] = bucket
                raise ApiError(429, "RATE_LIMITED", "请求过于频繁，请稍后重试")
            bucket.append(now)
            RATE_BUCKETS[key] = bucket
            if len(RATE_BUCKETS) > 5000:
                stale = [item for item, timestamps in RATE_BUCKETS.items() if not timestamps or now - timestamps[-1] > RATE_LIMIT_WINDOW_SECONDS]
                for item in stale[:1000]:
                    RATE_BUCKETS.pop(item, None)

    def _user(self, required=False):
        if DEMO_MODE and not required:
            return {"username": "demo", "role": "admin"}
        header = self.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else ""
        if not token:
            raise ApiError(401, "UNAUTHORIZED", "请先登录")
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with session() as db:
            db.execute("DELETE FROM sessions WHERE expires_at<?", (time.time(),))
            user = db.execute("SELECT s.username,u.role,s.expires_at FROM sessions s JOIN users u ON u.username=s.username WHERE s.token_hash=? AND u.enabled=1", (token_hash,)).fetchone()
            if not user or float(user["expires_at"]) < time.time():
                raise ApiError(401, "UNAUTHORIZED", "请先登录")
            db.execute("UPDATE sessions SET last_seen_at=CURRENT_TIMESTAMP WHERE token_hash=?", (token_hash,))
        return {"username": user["username"], "role": user["role"]}

    def _require_role(self, *roles):
        user = self._user(required=not DEMO_MODE)
        if not DEMO_MODE and user["role"] not in roles:
            raise ApiError(403, "FORBIDDEN", "当前角色无权执行此操作")
        return user

    def _file(self, path: Path):
        try:
            resolved = path.resolve()
            resolved.relative_to(FRONTEND.resolve())
        except (ValueError, OSError):
            raise ApiError(403, "FORBIDDEN_PATH", "禁止访问该路径")
        if not resolved.is_file():
            raise ApiError(404, "NOT_FOUND", "资源不存在")
        body = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(resolved.name)[0] or "application/octet-stream")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self._security_headers()
        if resolved.suffix.lower() == ".html":
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: http://127.0.0.1:8090 http://localhost:8090 https://tiles.openfreemap.org; connect-src 'self' http://127.0.0.1:8090 http://localhost:8090 https://tiles.openfreemap.org; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _mission_bundle(self, mission_id, db):
        mission = db.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
        if not mission:
            raise ApiError(404, "MISSION_NOT_FOUND", "任务不存在")
        result = dict(mission)
        result["checks"] = rows(db, "SELECT * FROM mission_checks WHERE mission_id=? ORDER BY id DESC", (mission_id,))
        result["routes"] = rows(db, "SELECT * FROM routes WHERE mission_id=? ORDER BY id DESC", (mission_id,))
        for route in result["routes"]:
            try:
                route["points"] = json.loads(route.pop("points_json"))
                route["terrain"] = route_terrain_metrics(route["points"], result["planned_altitude"])
            except (TypeError, ValueError, json.JSONDecodeError):
                route["points"] = []
                route["terrain"] = {"available": False, "sample_count": 0, "terrain_risk": "unknown"}
        result["events"] = rows(db, "SELECT id, event_type, severity, message, status, payload_json, created_at, resolved_at FROM events WHERE mission_id=? ORDER BY id", (mission_id,))
        for event in result["events"]:
            try:
                event["payload"] = json.loads(event.pop("payload_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                event["payload"] = {}
        result["replans"] = rows(db, "SELECT * FROM route_replans WHERE mission_id=? ORDER BY id", (mission_id,))
        flight = db.execute("SELECT * FROM flight_sessions WHERE mission_id=? ORDER BY id DESC LIMIT 1", (mission_id,)).fetchone()
        if flight:
            result["flight"] = dict(flight)
            try:
                result["flight"]["telemetry"] = json.loads(result["flight"].pop("telemetry_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                result["flight"]["telemetry"] = {}
        else:
            result["flight"] = None
        result["timeline"] = self._timeline_rows(mission_id, db)
        return result

    def _timeline_rows(self, mission_id, db):
        if not db.execute("SELECT 1 FROM missions WHERE id=?", (mission_id,)).fetchone():
            raise ApiError(404, "MISSION_NOT_FOUND", "任务不存在")
        timeline = []
        for item in db.execute("SELECT action, object_type, object_id, detail_json, actor_username, created_at FROM audit_logs WHERE object_id=? ORDER BY id", (mission_id,)).fetchall():
            try:
                detail = json.loads(item["detail_json"] or "{}")
            except json.JSONDecodeError:
                detail = {"raw": item["detail_json"]}
            timeline.append({"type": "audit", "action": item["action"], "at": item["created_at"], "actor": item["actor_username"], "detail": detail})
        for item in db.execute("SELECT id, event_type, severity, message, status, created_at, resolved_at FROM events WHERE mission_id=? ORDER BY id", (mission_id,)).fetchall():
            timeline.append({"type": "event", "action": item["event_type"], "at": item["created_at"], "actor": None, "detail": {"severity": item["severity"], "message": item["message"], "status": item["status"], "resolved_at": item["resolved_at"]}})
        for item in db.execute("SELECT id, decision, risk_level, created_at FROM mission_checks WHERE mission_id=? ORDER BY id", (mission_id,)).fetchall():
            timeline.append({"type": "check", "action": "rule_check", "at": item["created_at"], "actor": None, "detail": {"decision": item["decision"], "risk_level": item["risk_level"]}})
        for item in db.execute("SELECT id, name, distance_m, risk_level, created_at FROM routes WHERE mission_id=? ORDER BY id", (mission_id,)).fetchall():
            timeline.append({"type": "route", "action": "route_created", "at": item["created_at"], "actor": None, "detail": {"route_id": item["id"], "name": item["name"], "distance_m": item["distance_m"], "risk_level": item["risk_level"]}})
        for item in db.execute("SELECT id, event_id, route_id, reason, status, actor_username, created_at, confirmed_at FROM route_replans WHERE mission_id=? ORDER BY id", (mission_id,)).fetchall():
            timeline.append({"type": "replan", "action": "replan_" + item["status"], "at": item["confirmed_at"] or item["created_at"], "actor": item["actor_username"], "detail": {"replan_id": item["id"], "event_id": item["event_id"], "route_id": item["route_id"], "reason": item["reason"]}})
        timeline.sort(key=lambda entry: entry["at"] or "", reverse=True)
        return timeline

    def _mission_report_html(self, bundle):
        esc = lambda value: html.escape(str(value if value is not None else ""))
        mission = bundle
        rows_html = "".join(
            f"<tr><th>{esc(item['action'])}</th><td>{esc(item.get('at'))}</td><td>{esc(item.get('actor') or '系统')}</td><td>{esc(item.get('detail', {}).get('message') or item.get('detail', {}).get('reason') or item.get('detail', {}).get('decision') or '')}</td></tr>"
            for item in mission.get("timeline", [])
        )
        event_html = "".join(
            f"<li><strong>{esc(item.get('event_type'))}</strong> · {esc(item.get('severity'))} · {esc(item.get('status'))} · {esc(item.get('message'))}</li>"
            for item in mission.get("events", [])
        ) or "<li>无事件记录</li>"
        route_html = "".join(
            f"<li><strong>{esc(item.get('name'))}</strong> · {esc(item.get('risk_level'))} · {esc(item.get('distance_m'))} 米 · {esc(item.get('duration_s'))} 秒</li>"
            for item in mission.get("routes", [])
        ) or "<li>尚未生成航线</li>"
        return f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><title>梁平低空运行报告 - {esc(mission.get('id'))}</title>
<style>body{{font-family:Segoe UI,Microsoft YaHei,sans-serif;max-width:980px;margin:32px auto;padding:0 20px;color:#1d2730}}h1{{margin-bottom:4px}}h2{{margin-top:28px;border-bottom:1px solid #ccd5da;padding-bottom:6px}}.meta{{color:#52616b}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccd5da;padding:8px;text-align:left;vertical-align:top}}th{{background:#eef3f5}}li{{margin:6px 0}}</style></head>
<body><h1>梁平低空运行全过程报告</h1><p class='meta'>任务：{esc(mission.get('id'))} · 生成时间：{esc(datetime.now(timezone.utc).isoformat())}</p>
<h2>任务摘要</h2><table><tr><th>名称</th><td>{esc(mission.get('name'))}</td><th>状态</th><td>{esc(mission.get('status_label'))}</td></tr><tr><th>飞行器</th><td>{esc(mission.get('vehicle_id'))}</td><th>计划高度</th><td>{esc(mission.get('planned_altitude'))} 米</td></tr><tr><th>起点</th><td>{esc(mission.get('start_lng'))}, {esc(mission.get('start_lat'))}</td><th>终点</th><td>{esc(mission.get('end_lng'))}, {esc(mission.get('end_lat'))}</td></tr></table>
<h2>航线记录</h2><ul>{route_html}</ul><h2>事件与告警</h2><ul>{event_html}</ul><h2>全过程时间线</h2><table><thead><tr><th>动作</th><th>时间</th><th>操作者</th><th>说明</th></tr></thead><tbody>{rows_html or '<tr><td colspan="4">无时间线记录</td></tr>'}</tbody></table>
</body></html>"""

    def do_GET(self):  # noqa: N802
        try:
            route = urlparse(self.path).path
            if route == "/api/map/config":
                provider = "OpenFreeMap" if "tiles.openfreemap.org" in MAP_STYLE_URL else "OpenMapTiles" if MAP_STYLE_URL else "local-reference"
                self._json({"style_url": MAP_STYLE_URL, "provider": provider})
                return
            if route == "/api/health":
                capabilities = database_capabilities()
                try:
                    storage = build_storage()
                    self._json({"status": "ok", "service": "liangping-low-altitude-base", "version": ENGINE_VERSION, "uptime_s": round(time.time() - STARTED_AT, 1), "database": {**capabilities, "adapter": storage.info.backend, "adapter_ready": storage.info.ready}})
                except Exception as error:
                    print(f"health check failed: {error}")
                    self._json({"status": "unavailable", "service": "liangping-low-altitude-base", "database": capabilities}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            if route == "/api/health/deep":
                if not DEMO_MODE:
                    self._user(required=True)
                try:
                    storage = build_storage()
                    self._json({"status": "ready", "database": storage.info.__dict__, "deep": storage.deep_health()})
                except Exception as error:
                    print(f"deep health failed: {error}")
                    self._json({"status": "unavailable", "error": "数据库健康检查失败"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            if route == "/api/metrics":
                if not DEMO_MODE:
                    self._user(required=True)
                with session() as db:
                    counts = {"missions": db.execute("SELECT COUNT(*) FROM missions").fetchone()[0], "running_missions": db.execute("SELECT COUNT(*) FROM missions WHERE status='running'").fetchone()[0], "open_events": db.execute("SELECT COUNT(*) FROM events WHERE status='open'").fetchone()[0], "active_sessions": db.execute("SELECT COUNT(*) FROM sessions WHERE expires_at>?", (time.time(),)).fetchone()[0]}
                with RATE_LOCK:
                    requests_tracked = sum(len(item) for item in RATE_BUCKETS.values())
                self._json({"status": "ok", "uptime_s": round(time.time() - STARTED_AT, 1), "requests_tracked": requests_tracked, "counts": counts})
                return
            if route.startswith("/api/") and route not in {"/api/auth/login", "/api/auth/logout"}:
                self._user(required=not DEMO_MODE)
            if route == "/api/auth/me":
                self._json(self._user(required=True)); return
            if route == "/api/demo/status":
                with session() as db:
                    self._json({"layers": db.execute("SELECT COUNT(*) FROM layers").fetchone()[0], "missions": db.execute("SELECT COUNT(*) FROM missions").fetchone()[0], "audit_logs": db.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]})
                return
            if route == "/api/audit-logs":
                query = parse_qs(urlparse(self.path).query)
                conditions, params = [], []
                for key in ("object_type", "object_id", "action", "actor_username"):
                    value = str(query.get(key, [""])[0]).strip()
                    if value:
                        conditions.append(f"{key}=?")
                        params.append(value)
                limit = max(1, min(int(query.get("limit", ["100"])[0]), 500))
                sql = "SELECT * FROM audit_logs" + (" WHERE " + " AND ".join(conditions) if conditions else "") + " ORDER BY id DESC LIMIT ?"
                params.append(limit)
                with session() as db:
                    self._json(rows(db, sql, tuple(params)))
                return
            with session() as db:
                resources = {
                    "/api/layers": "SELECT * FROM layers ORDER BY id",
                    "/api/vehicles": "SELECT * FROM vehicles ORDER BY id",
                    "/api/missions": "SELECT * FROM missions ORDER BY created_at DESC, id DESC",
                    "/api/rules": "SELECT * FROM rules WHERE enabled=1 ORDER BY code",
                    "/api/airspace-cells": "SELECT * FROM airspace_cells ORDER BY cell_id",
                    "/api/facilities": "SELECT * FROM facilities ORDER BY facility_id",
                    "/api/audit-logs": "SELECT * FROM audit_logs ORDER BY id DESC LIMIT 100",
                }
                if route == "/api/bootstrap":
                    payload = {key[5:]: rows(db, query) for key, query in resources.items() if key != "/api/audit-logs"}
                    try:
                        spatial = json.loads(SPATIAL_ASSETS.read_text(encoding="utf-8")) if SPATIAL_ASSETS.exists() else {"type": "FeatureCollection", "features": []}
                    except (OSError, json.JSONDecodeError):
                        spatial = {"type": "FeatureCollection", "features": []}
                    payload["spatial_assets"] = spatial
                    payload["map_features"] = build_map_feature_collection(db, SPATIAL_ASSETS)
                    payload["traceability"] = traceability()
                    payload["airspace_cells"] = rows(db, resources["/api/airspace-cells"])
                    payload["facilities"] = rows(db, resources["/api/facilities"])
                    self._json(payload)
                    return
                if route == "/api/spatial-assets":
                    try:
                        self._json(json.loads(SPATIAL_ASSETS.read_text(encoding="utf-8")))
                    except (OSError, json.JSONDecodeError):
                        raise ApiError(503, "SPATIAL_ASSETS_UNAVAILABLE", "公开参考空间资产尚未准备")
                    return
                if route == "/api/map/features":
                    self._json(build_map_feature_collection(db, SPATIAL_ASSETS))
                    return
                if route == "/api/elevation/grid":
                    try:
                        self._json(json.loads(DEM_GRID.read_text(encoding="utf-8")))
                    except (OSError, json.JSONDecodeError):
                        raise ApiError(503, "DEM_UNAVAILABLE", "梁平高程网格尚未准备")
                    return
                if route == "/api/elevation/grid":
                    try:
                        self._json(json.loads(DEM_GRID.read_text(encoding="utf-8")))
                    except (OSError, json.JSONDecodeError):
                        raise ApiError(503, "DEM_UNAVAILABLE", "梁平高程网格尚未准备")
                    return
                if route in resources:
                    self._json(rows(db, resources[route]))
                    return
                mission_match = re.fullmatch(r"/api/missions/([^/]+)", route)
                if mission_match:
                    mission = db.execute("SELECT * FROM missions WHERE id=?", (mission_match.group(1),)).fetchone()
                    if not mission:
                        raise ApiError(404, "MISSION_NOT_FOUND", "任务不存在")
                    result = dict(mission)
                    result["checks"] = rows(db, "SELECT * FROM mission_checks WHERE mission_id=? ORDER BY id DESC", (result["id"],))
                    result["routes"] = rows(db, "SELECT * FROM routes WHERE mission_id=? ORDER BY id DESC", (result["id"],))
                    result["replans"] = rows(db, "SELECT * FROM route_replans WHERE mission_id=? ORDER BY id DESC", (result["id"],))
                    self._json(result)
                    return
                timeline_match = re.fullmatch(r"/api/missions/([^/]+)/timeline", route)
                if timeline_match:
                    self._mission_timeline(timeline_match.group(1), db)
                    return
                route_match = re.fullmatch(r"/api/missions/([^/]+)/routes", route)
                if route_match:
                    self._json(rows(db, "SELECT * FROM routes WHERE mission_id=? ORDER BY id DESC", (route_match.group(1),)))
                    return
                decision_match = re.fullmatch(r"/api/missions/([^/]+)/route-decisions", route)
                if decision_match:
                    self._json(rows(db, "SELECT * FROM route_decisions WHERE mission_id=? ORDER BY id DESC", (decision_match.group(1),)))
                    return
                event_match = re.fullmatch(r"/api/missions/([^/]+)/events", route)
                if event_match:
                    event_query = parse_qs(urlparse(self.path).query)
                    status = str(event_query.get("status", [""])[0]).strip()
                    if status not in {"", "open", "resolved"}:
                        raise ApiError(422, "INVALID_EVENT_STATUS", "事件状态仅支持 open 或 resolved")
                    sql = "SELECT * FROM events WHERE mission_id=?" + (" AND status=?" if status else "") + " ORDER BY id DESC"
                    params = (event_match.group(1), status) if status else (event_match.group(1),)
                    self._json(rows(db, sql, params))
                    return
                flight_match = re.fullmatch(r"/api/missions/([^/]+)/flight", route)
                if flight_match:
                    flight = db.execute("SELECT * FROM flight_sessions WHERE mission_id=? ORDER BY id DESC LIMIT 1", (flight_match.group(1),)).fetchone()
                    if not flight: raise ApiError(404, "FLIGHT_NOT_FOUND", "尚未启动模拟飞行")
                    result = dict(flight); result["telemetry"] = json.loads(result.pop("telemetry_json")); self._json(result); return
                telemetry_match = re.fullmatch(r"/api/missions/([^/]+)/telemetry", route)
                if telemetry_match:
                    flight = db.execute("SELECT * FROM flight_sessions WHERE mission_id=? ORDER BY id DESC LIMIT 1", (telemetry_match.group(1),)).fetchone()
                    if not flight:
                        raise ApiError(404, "TELEMETRY_NOT_FOUND", "该任务尚无遥测记录")
                    result = dict(flight); result["telemetry"] = json.loads(result.pop("telemetry_json")); self._json(result); return
                track_match = re.fullmatch(r"/api/missions/([^/]+)/telemetry/track", route)
                if track_match:
                    mission = db.execute("SELECT id FROM missions WHERE id=?", (track_match.group(1),)).fetchone()
                    if not mission:
                        raise ApiError(404, "MISSION_NOT_FOUND", "任务不存在")
                    flight = db.execute("SELECT id FROM flight_sessions WHERE mission_id=? ORDER BY id DESC LIMIT 1", (track_match.group(1),)).fetchone()
                    samples = self._telemetry_track(track_match.group(1), db, flight["id"]) if flight else []
                    track_query = parse_qs(urlparse(self.path).query)
                    output_format = str(track_query.get("format", ["json"])[0]).lower()
                    if output_format not in {"json", "csv"}:
                        raise ApiError(422, "INVALID_TRACK_FORMAT", "轨迹格式仅支持 json 或 csv")
                    if output_format == "csv":
                        csv_body = telemetry_track_csv(samples)
                        filename = re.sub(r"[^A-Za-z0-9_-]", "_", track_match.group(1))
                        self._text(csv_body, "text/csv; charset=utf-8", extra_headers={"Content-Disposition": f'attachment; filename="{filename}-track.csv"'})
                    else:
                        self._json({"mission_id": track_match.group(1), "session_id": flight["id"] if flight else None, "samples": samples, "available": bool(flight), "message": None if flight else "暂无可回放轨迹"})
                    return
            self._file(FRONTEND / ("index.html" if route in ("/", "/index.html") else route.lstrip("/")))
        except ApiError as error:
            self._error(error)
        except Exception as error:
            print(f"internal error on {self.command} {self.path}: {error}")
            self._error(ApiError(500, "INTERNAL_ERROR", "服务暂时无法处理请求"))

    def do_POST(self):  # noqa: N802
        try:
            route = urlparse(self.path).path
            self._rate_limit()
            if route == "/api/auth/login":
                payload = self._body(); username, password = payload.get("username", ""), payload.get("password", "")
                with session() as db:
                    user = db.execute("SELECT username,role,password_hash,failed_attempts,locked_until FROM users WHERE username=? AND enabled=1", (username,)).fetchone()
                    if user and user["locked_until"] > time.time():
                        raise ApiError(429, "ACCOUNT_LOCKED", "登录失败次数过多，请稍后再试")
                valid, legacy = (False, False) if not user else verify_password(password, user["password_hash"])
                if not valid:
                    with session() as audit_db:
                        audit_db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json,actor_username) VALUES(?,?,?,?,?)", ("login_failed", "user", username or "unknown", "{}", username or "unknown"))
                        if user:
                            attempts = user["failed_attempts"] + 1
                            locked_until = time.time() + 900 if attempts >= 5 else 0
                            audit_db.execute("UPDATE users SET failed_attempts=?,locked_until=? WHERE username=?", (attempts, locked_until, username))
                    raise ApiError(401, "INVALID_CREDENTIALS", "用户名或密码错误")
                with session() as db:
                    if legacy:
                        db.execute("UPDATE users SET password_hash=?,failed_attempts=0,locked_until=0 WHERE username=?", (hash_password(password), username))
                    else:
                        db.execute("UPDATE users SET failed_attempts=0,locked_until=0 WHERE username=?", (username,))
                token = secrets.token_urlsafe(32)
                token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
                with session() as db:
                    db.execute("DELETE FROM sessions WHERE expires_at<?", (time.time(),))
                    db.execute("INSERT INTO sessions(token_hash,username,expires_at,ip_address,user_agent) VALUES(?,?,?,?,?)", (token_hash, user["username"], time.time() + SESSION_TTL_SECONDS, self.client_address[0], self.headers.get("User-Agent", "")[:512]))
                self._json({"token": token, "username": user["username"], "role": user["role"]}); return
            if route == "/api/auth/change-password":
                actor = self._user(required=True); payload = self._body(); old, new = payload.get("old_password", ""), payload.get("new_password", "")
                if len(new) < 8: raise ApiError(422, "WEAK_PASSWORD", "新密码至少需要8位")
                with session() as db:
                    user = db.execute("SELECT password_hash FROM users WHERE username=?", (actor["username"],)).fetchone()
                    valid, _ = (False, False) if not user else verify_password(old, user["password_hash"])
                    if not valid: raise ApiError(401, "INVALID_PASSWORD", "原密码错误")
                    db.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_password(new), actor["username"]))
                    db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json,actor_username) VALUES(?,?,?,?,?)", ("password_change", "user", actor["username"], "{}", actor["username"]))
                self._json({"status":"changed"}); return
            if route == "/api/auth/logout":
                header = self.headers.get("Authorization", "")
                if header.startswith("Bearer "):
                    token_hash = hashlib.sha256(header[7:].encode("utf-8")).hexdigest()
                    with session() as db:
                        db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
                self._json({"status": "logged_out"}); return
            if route == "/api/demo/reset":
                if not DEMO_MODE:
                    raise ApiError(403, "DEMO_ONLY", "演示数据重置仅允许在 DEMO_MODE=true 时使用")
                self._require_role("admin")
                if database_capabilities()["backend"] != "sqlite":
                    raise ApiError(409, "DEMO_RESET_SQLITE_ONLY", "演示重置仅支持 SQLite 离线模式")
                init_db(reset=True)
                self._json({"status":"reset","message":"演示数据已重置"})
                return
            if route == "/api/layers/import":
                self._require_role("admin", "dispatcher")
                self._import_layer(self._body())
                return
            facility_match = re.fullmatch(r"/api/facilities(?:/([^/]+))?", route)
            if facility_match:
                actor = self._require_role("admin", "dispatcher")
                facility_id = facility_match.group(1)
                if self.command == "POST" and facility_id is None:
                    self._create_facility(self._body(), actor["username"]); return
                if self.command == "PATCH" and facility_id:
                    self._update_facility(facility_id, self._body(), actor["username"]); return
                if self.command == "DELETE" and facility_id:
                    self._disable_facility(facility_id, actor["username"]); return
                raise ApiError(405, "METHOD_NOT_ALLOWED", "设施接口方法不支持")
            start_match = re.fullmatch(r"/api/missions/([^/]+)/flight/start", route)
            event_match = re.fullmatch(r"/api/missions/([^/]+)/events", route)
            resolve_match = re.fullmatch(r"/api/events/(\d+)/resolve", route)
            replan_match = re.fullmatch(r"/api/missions/([^/]+)/replan", route)
            confirm_replan_match = re.fullmatch(r"/api/replans/(\d+)/confirm", route)
            route_decision_match = re.fullmatch(r"/api/missions/([^/]+)/routes/(\d+)/(adopt|return|revoke)", route)
            tick_match = re.fullmatch(r"/api/missions/([^/]+)/flight/tick", route)
            telemetry_match = re.fullmatch(r"/api/missions/([^/]+)/telemetry", route)
            if start_match:
                self._require_role("admin", "dispatcher")
                self._start_flight(start_match.group(1)); return
            if event_match:
                self._require_role("admin", "dispatcher")
                self._inject_event(event_match.group(1), self._body()); return
            if resolve_match:
                self._require_role("admin", "dispatcher")
                self._resolve_event(int(resolve_match.group(1))); return
            if confirm_replan_match:
                actor = self._require_role("admin", "dispatcher")
                self._confirm_replan(int(confirm_replan_match.group(1)), actor["username"]); return
            if route_decision_match:
                actor = self._require_role("admin", "dispatcher")
                self._decide_route(route_decision_match.group(1), int(route_decision_match.group(2)), route_decision_match.group(3), self._body(), actor["username"])
                return
            if tick_match:
                self._require_role("admin", "dispatcher")
                self._tick_flight(tick_match.group(1), self._body()); return
            if telemetry_match:
                self._require_role("admin", "dispatcher")
                self._ingest_telemetry(telemetry_match.group(1), self._body()); return
            publish_match = re.fullmatch(r"/api/layers/(\d+)/(publish|disable)", route)
            if publish_match:
                self._require_role("admin", "dispatcher")
                self._set_layer_status(int(publish_match.group(1)), publish_match.group(2))
                return
            if route != "/api/missions":
                check_match = re.fullmatch(r"/api/missions/([^/]+)/check", route)
                plan_match = re.fullmatch(r"/api/missions/([^/]+)/routes/plan", route)
                if check_match:
                    self._require_role("admin", "dispatcher")
                    self._check_mission(check_match.group(1))
                    return
                if plan_match:
                    self._require_role("admin", "dispatcher")
                    self._plan_route(plan_match.group(1))
                    return
                if replan_match:
                    actor = self._require_role("admin", "dispatcher")
                    self._propose_replan(replan_match.group(1), self._body(), actor["username"])
                    return
                raise ApiError(404, "NOT_FOUND", "接口不存在")
            self._require_role("admin", "dispatcher")
            payload = validate_mission(self._body())
            with session() as db:
                if not db.execute("SELECT 1 FROM vehicles WHERE id=?", (payload["vehicle_id"],)).fetchone():
                    raise ApiError(422, "VEHICLE_NOT_FOUND", "所选飞行器不存在")
                try:
                    db.execute(
                        """INSERT INTO missions(id,name,vehicle_id,route_name,start_lng,start_lat,end_lng,end_lat,planned_altitude,time_window_start,time_window_end,status,status_label)
                        VALUES(:id,:name,:vehicle_id,:route_name,:start_lng,:start_lat,:end_lng,:end_lat,:planned_altitude,:time_window_start,:time_window_end,'planned','已计划')""",
                        payload,
                    )
                except sqlite3.IntegrityError:
                    raise ApiError(409, "MISSION_EXISTS", "任务编号已经存在")
                except Exception as error:
                    if getattr(error, "sqlstate", None) == "23505":
                        raise ApiError(409, "MISSION_EXISTS", "任务编号已经存在") from error
                    raise
                db.execute(
                    "INSERT INTO audit_logs(action,object_type,object_id,detail_json) VALUES(?,?,?,?)",
                    ("create", "mission", payload["id"], json.dumps(payload, ensure_ascii=False)),
                )
            self._json({**payload, "status": "planned", "status_label": "已计划"}, HTTPStatus.CREATED)
        except ApiError as error:
            self._error(error)
        except Exception as error:
            print(f"internal error on {self.command} {self.path}: {error}")
            self._error(ApiError(500, "INTERNAL_ERROR", "服务暂时无法处理请求"))

    def do_PATCH(self):  # noqa: N802
        self.do_POST()

    def do_DELETE(self):  # noqa: N802
        self.do_POST()

    def _facility_payload(self, payload, existing=None):
        data = dict(existing or {})
        data.update(payload or {})
        required = ("facility_id", "facility_type", "name", "longitude", "latitude")
        missing = [key for key in required if data.get(key) in (None, "")]
        if missing:
            raise ApiError(422, "MISSING_FIELDS", "缺少字段: " + ", ".join(missing))
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{2,39}", str(data["facility_id"])):
            raise ApiError(422, "INVALID_FACILITY_ID", "设施编号格式不合法")
        try:
            data["longitude"], data["latitude"] = float(data["longitude"]), float(data["latitude"])
        except (TypeError, ValueError):
            raise ApiError(422, "INVALID_COORDINATE", "设施坐标必须为数字")
        if not 105 <= data["longitude"] <= 110 or not 28 <= data["latitude"] <= 32:
            raise ApiError(422, "OUT_OF_DEMO_AREA", "设施坐标超出演示区域")
        data["status"] = data.get("status", "active")
        if data["status"] not in ("active", "maintenance", "disabled"):
            raise ApiError(422, "INVALID_FACILITY_STATUS", "设施状态不合法")
        compatible = data.get("compatible_vehicles_json", data.get("compatible_vehicles", []))
        if isinstance(compatible, str):
            try: compatible = json.loads(compatible)
            except json.JSONDecodeError: raise ApiError(422, "INVALID_COMPATIBLE_VEHICLES", "兼容飞行器必须是 JSON 数组")
        if not isinstance(compatible, list):
            raise ApiError(422, "INVALID_COMPATIBLE_VEHICLES", "兼容飞行器必须是数组")
        data["compatible_vehicles_json"] = json.dumps(compatible, ensure_ascii=False)
        data.setdefault("opening_hours", ""); data.setdefault("source_kind", "synthetic_demo"); data.setdefault("data_version", "demo-1")
        return data

    def _create_facility(self, payload, actor_username):
        data = self._facility_payload(payload)
        with session() as db:
            if db.execute("SELECT 1 FROM facilities WHERE facility_id=?", (data["facility_id"],)).fetchone():
                raise ApiError(409, "FACILITY_EXISTS", "设施编号已经存在")
            db.execute("""INSERT INTO facilities(facility_id,facility_type,name,longitude,latitude,elevation_m,capacity,service_radius_m,opening_hours,compatible_vehicles_json,status,source_kind,data_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (data["facility_id"],data["facility_type"],data["name"],data["longitude"],data["latitude"],data.get("elevation_m"),data.get("capacity"),data.get("service_radius_m"),data["opening_hours"],data["compatible_vehicles_json"],data["status"],data["source_kind"],data["data_version"]))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json,actor_username) VALUES(?,?,?,?,?)", ("facility_create","facility",data["facility_id"],json.dumps(payload,ensure_ascii=False),actor_username))
        self._json(data, HTTPStatus.CREATED)

    def _update_facility(self, facility_id, payload, actor_username):
        with session() as db:
            row = db.execute("SELECT * FROM facilities WHERE facility_id=?", (facility_id,)).fetchone()
            if not row: raise ApiError(404, "FACILITY_NOT_FOUND", "设施不存在")
            data = self._facility_payload({**payload, "facility_id": facility_id}, dict(row))
            db.execute("""UPDATE facilities SET facility_type=?,name=?,longitude=?,latitude=?,elevation_m=?,capacity=?,service_radius_m=?,opening_hours=?,compatible_vehicles_json=?,status=?,data_version=?,updated_at=CURRENT_TIMESTAMP WHERE facility_id=?""", (data["facility_type"],data["name"],data["longitude"],data["latitude"],data.get("elevation_m"),data.get("capacity"),data.get("service_radius_m"),data["opening_hours"],data["compatible_vehicles_json"],data["status"],data["data_version"],facility_id))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json,actor_username) VALUES(?,?,?,?,?)", ("facility_update","facility",facility_id,json.dumps(payload,ensure_ascii=False),actor_username))
        self._json(data)

    def _disable_facility(self, facility_id, actor_username):
        with session() as db:
            if not db.execute("SELECT 1 FROM facilities WHERE facility_id=?", (facility_id,)).fetchone(): raise ApiError(404, "FACILITY_NOT_FOUND", "设施不存在")
            db.execute("UPDATE facilities SET status='disabled',updated_at=CURRENT_TIMESTAMP WHERE facility_id=?", (facility_id,))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json,actor_username) VALUES(?,?,?,?,?)", ("facility_disable","facility",facility_id,"{}",actor_username))
        self._json({"facility_id": facility_id, "status": "disabled"})

    def _import_layer(self, payload):
        if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list) or not payload["features"]:
            raise ApiError(422, "INVALID_GEOJSON", "必须提供非空 FeatureCollection")
        if len(payload["features"]) != 1:
            raise ApiError(422, "MULTI_FEATURE_UNSUPPORTED", "当前版本一次只允许导入一个 Polygon 图层")
        name = payload.get("name") or "导入图层"
        layer_type = payload.get("layer_type", "restricted")
        level = payload.get("level", "hard")
        if layer_type not in ("restricted", "operable") or level not in ("hard", "soft", "temporary", "open"):
            raise ApiError(422, "INVALID_LAYER_ATTRIBUTES", "图层类型或限制等级不合法")
        for feature in payload["features"]:
            geometry = feature.get("geometry", {})
            coords = geometry.get("coordinates")
            if geometry.get("type") != "Polygon" or not coords or not coords[0] or len(coords[0]) < 4 or coords[0][0] != coords[0][-1]:
                raise ApiError(422, "INVALID_GEOMETRY", "当前仅支持闭合 Polygon，且至少需要4个坐标点")
            for point in coords[0]:
                try:
                    valid_point = isinstance(point, list) and len(point) >= 2 and 105 <= float(point[0]) <= 110 and 28 <= float(point[1]) <= 32
                except (TypeError, ValueError):
                    valid_point = False
                if not valid_point:
                    raise ApiError(422, "INVALID_COORDINATE", "坐标必须位于梁平演示区域范围")
        with session() as db:
            layer_id = insert_returning_id(db, "INSERT INTO layers(name,layer_type,level,geometry_json,status,source) VALUES(?,?,?,?,?,?)", (name, layer_type, level, json.dumps(payload["features"][0]["geometry"], ensure_ascii=False), "draft", "import"))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json) VALUES(?,?,?,?)", ("import", "layer", str(layer_id), json.dumps({"name":name}, ensure_ascii=False)))
            self._json({"id":layer_id,"name":name,"status":"draft","message":"图层校验通过，等待发布"}, HTTPStatus.CREATED)

    def _set_layer_status(self, layer_id, action):
        status = "published" if action == "publish" else "disabled"
        with session() as db:
            if not db.execute("SELECT 1 FROM layers WHERE id=?", (layer_id,)).fetchone():
                raise ApiError(404, "LAYER_NOT_FOUND", "图层不存在")
            db.execute("UPDATE layers SET status=? WHERE id=?", (status, layer_id))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json) VALUES(?,?,?,?)", (action, "layer", str(layer_id), json.dumps({"status":status})))
            self._json({"id":layer_id,"status":status})

    def _check_mission(self, mission_id):
        with session() as db:
            mission = db.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
            if not mission:
                raise ApiError(404, "MISSION_NOT_FOUND", "任务不存在")
            items = []
            if mission["planned_altitude"] > 1200:
                items.append({"rule_code":"R-002","level":"hard","message":"计划高度超过1200米","action":"调整飞行高度"})
            start, end = (mission["start_lng"], mission["start_lat"]), (mission["end_lng"], mission["end_lat"])
            for layer in db.execute("SELECT * FROM layers WHERE status='published'").fetchall():
                geometry = json.loads(layer["geometry_json"])
                if segment_intersects_polygon(start, end, geometry):
                    level = "hard" if layer["level"] == "hard" else "soft"
                    items.append({"rule_code":"R-001" if level == "hard" else "R-003","level":level,"message":f"航线穿越{layer['name']}","action":"调整航线" if level == "hard" else "人工确认后继续"})
            facility_check = facility_reachability(db, mission)
            if not facility_check["start"]["reachable"]:
                items.append({"rule_code": "F-001", "level": "hard", "message": "起点没有满足机型兼容和服务半径的可用设施", "action": "调整起点或启用备降设施"})
            if not facility_check["end"]["reachable"]:
                items.append({"rule_code": "F-002", "level": "hard", "message": "终点没有满足机型兼容和服务半径的可用设施", "action": "调整终点或启用备降设施"})
            altitude = float(mission["planned_altitude"])
            for cell in db.execute("SELECT * FROM airspace_cells WHERE status='published'").fetchall():
                try:
                    geometry = json.loads(cell["geometry_json"])
                except (TypeError, json.JSONDecodeError):
                    continue
                spatial_hit = segment_intersects_polygon(start, end, geometry)
                altitude_hit = (cell["min_altitude_m"] is None or altitude >= float(cell["min_altitude_m"])) and (cell["max_altitude_m"] is None or altitude <= float(cell["max_altitude_m"]))
                temporal_hit = windows_overlap(mission["time_window_start"], mission["time_window_end"], cell["valid_from"], cell["valid_to"])
                if spatial_hit and altitude_hit and (temporal_hit or not cell["valid_from"]):
                    level = "hard" if cell["risk_level"] == "high" else "soft"
                    items.append({"rule_code": "A-001", "level": level, "message": f"航线进入四维空域单元 {cell['cell_id']}（{cell['min_altitude_m']}-{cell['max_altitude_m']}m）", "action": "调整高度/航线或人工确认", "cell_id": cell["cell_id"], "rule_version": cell["rule_version"], "data_version": cell["data_version"]})
            decision = "blocked" if any(x["level"] == "hard" for x in items) else ("warning" if items else "pass")
            risk = "high" if decision == "blocked" else ("medium" if items else "low")
            detail = {"decision": decision, "risk_level": risk, "facility": facility_check, "traceability": traceability()}
            db.execute("INSERT INTO mission_checks(mission_id,decision,risk_level,items_json) VALUES(?,?,?,?)", (mission_id, decision, risk, json.dumps({"items": items, **detail}, ensure_ascii=False)))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json) VALUES(?,?,?,?)", ("check", "mission", mission_id, json.dumps(detail, ensure_ascii=False)))
            self._json({"mission_id":mission_id,"decision":decision,"risk_level":risk,"items":items,"facility":facility_check,"traceability":traceability()})

    def _plan_route(self, mission_id):
        with session() as db:
            mission = db.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
            if not mission: raise ApiError(404, "MISSION_NOT_FOUND", "任务不存在")
            latest = db.execute("SELECT * FROM mission_checks WHERE mission_id=? ORDER BY id DESC LIMIT 1", (mission_id,)).fetchone()
            if not latest:
                raise ApiError(409, "CHECK_REQUIRED", "请先执行规则检查")
            if latest["decision"] == "blocked":
                raise ApiError(409, "ROUTE_BLOCKED", "规则检查未通过，不能生成航线")
            points = [[mission["start_lng"], mission["start_lat"], mission["planned_altitude"]], [mission["end_lng"], mission["end_lat"], mission["planned_altitude"]]]
            distance = haversine(points[0][0], points[0][1], points[1][0], points[1][1])
            duration = distance / 12
            route_id = insert_returning_id(db, "INSERT INTO routes(mission_id,name,points_json,distance_m,duration_s,risk_level) VALUES(?,?,?,?,?,?)", (mission_id, "主航线-直连", json.dumps(points), distance, duration, "medium" if latest["decision"] == "warning" else "low"))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json) VALUES(?,?,?,?)", ("plan", "route", str(route_id), json.dumps({"mission_id":mission_id}, ensure_ascii=False)))
            self._json({"id":route_id,"mission_id":mission_id,"name":"主航线-直连","points":points,"distance_m":round(distance,1),"duration_s":round(duration,1),"risk_level":"medium" if latest["decision"] == "warning" else "low"}, HTTPStatus.CREATED)

    def _decide_route(self, mission_id, route_id, action, payload, actor_username):
        decision = {"adopt": "adopted", "return": "returned", "revoke": "revoked"}[action]
        with session() as db:
            route = db.execute("SELECT id FROM routes WHERE id=? AND mission_id=?", (route_id, mission_id)).fetchone()
            if not route:
                raise ApiError(404, "ROUTE_NOT_FOUND", "任务航线不存在")
            reason = str(payload.get("reason", "")).strip()[:500] or None
            db.execute("INSERT INTO route_decisions(mission_id,route_id,decision,reason,actor_username) VALUES(?,?,?,?,?)", (mission_id, route_id, decision, reason, actor_username))
            if decision == "adopted":
                db.execute("UPDATE missions SET route_name=(SELECT name FROM routes WHERE id=?), status='planned', status_label='已计划' WHERE id=?", (route_id, mission_id))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json,actor_username) VALUES(?,?,?,?,?)", ("route_" + decision, "route", str(route_id), json.dumps({"mission_id": mission_id, "reason": reason}, ensure_ascii=False), actor_username))
            self._json({"mission_id": mission_id, "route_id": route_id, "decision": decision, "reason": reason, "actor_username": actor_username}, HTTPStatus.CREATED)

    def _start_flight(self, mission_id):
        with session() as db:
            mission = db.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
            if not mission: raise ApiError(404, "MISSION_NOT_FOUND", "任务不存在")
            active = db.execute("SELECT 1 FROM flight_sessions WHERE mission_id=? AND status='running'", (mission_id,)).fetchone()
            if active: raise ApiError(409, "FLIGHT_ALREADY_RUNNING", "该任务已经在模拟飞行中")
            route = db.execute("SELECT * FROM routes WHERE mission_id=? ORDER BY id DESC LIMIT 1", (mission_id,)).fetchone()
            if not route: raise ApiError(409, "ROUTE_REQUIRED", "请先生成航线")
            telemetry = normalize_telemetry({"longitude": mission["start_lng"], "latitude": mission["start_lat"], "altitude": mission["planned_altitude"], "battery": 100, "link_quality": 100, "status": "airborne", "source": "simulator"})
            session_id = insert_returning_id(db, "INSERT INTO flight_sessions(mission_id,status,progress,telemetry_json,started_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP)", (mission_id, "running", 0, json.dumps(telemetry)))
            self._record_telemetry_sample(db, mission_id, session_id, telemetry)
            db.execute("UPDATE missions SET status='running',status_label='运行中' WHERE id=?", (mission_id,))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json) VALUES(?,?,?,?)", ("flight_start", "mission", mission_id, json.dumps(telemetry, ensure_ascii=False)))
            self._json({"session_id":session_id,"mission_id":mission_id,"status":"running","progress":0,"telemetry":telemetry}, HTTPStatus.CREATED)

    def _inject_event(self, mission_id, payload):
        allowed = {"deviation":("warning","发生航线偏航"),"low_battery":("critical","飞行器电量不足"),"link_loss":("critical","飞行器链路中断"),"temporary_restriction":("critical","前方出现临时限制区")}
        event_type = payload.get("event_type")
        if event_type not in allowed: raise ApiError(422, "INVALID_EVENT_TYPE", "不支持的事件类型")
        with session() as db:
            if not db.execute("SELECT 1 FROM missions WHERE id=?", (mission_id,)).fetchone(): raise ApiError(404, "MISSION_NOT_FOUND", "任务不存在")
            severity, message = allowed[event_type]
            event_id = insert_returning_id(db, "INSERT INTO events(mission_id,event_type,severity,message,payload_json) VALUES(?,?,?,?,?)", (mission_id,event_type,severity,message,json.dumps(payload,ensure_ascii=False)))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json) VALUES(?,?,?,?)", ("event", "mission", mission_id, json.dumps(payload, ensure_ascii=False)))
            self._json({"id":event_id,"mission_id":mission_id,"event_type":event_type,"severity":severity,"message":message,"status":"open"}, HTTPStatus.CREATED)

    def _tick_flight(self, mission_id, payload):
        step = float(payload.get("step", 10))
        if not 1 <= step <= 50: raise ApiError(422, "INVALID_STEP", "推进步长必须在1至50之间")
        with session() as db:
            flight = db.execute("SELECT * FROM flight_sessions WHERE mission_id=? ORDER BY id DESC LIMIT 1", (mission_id,)).fetchone()
            mission = db.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
            if not flight or not mission: raise ApiError(404, "FLIGHT_NOT_FOUND", "尚未启动模拟飞行")
            if flight["status"] != "running":
                raise ApiError(409, "FLIGHT_NOT_RUNNING", f"当前飞行状态为 {flight['status']}，不能推进")
            telemetry = json.loads(flight["telemetry_json"]); progress = min(100, flight["progress"] + step)
            ratio = progress / 100
            telemetry["longitude"] = mission["start_lng"] + (mission["end_lng"] - mission["start_lng"]) * ratio
            telemetry["latitude"] = mission["start_lat"] + (mission["end_lat"] - mission["start_lat"]) * ratio
            telemetry["battery"] = max(0, round(100 - progress * 0.35, 1))
            telemetry["speed"] = 12.0
            telemetry["status"] = "completed" if progress >= 100 else "airborne"
            telemetry["timestamp"] = datetime.now(timezone.utc).isoformat()
            telemetry["source"] = "simulator"
            status = "completed" if progress >= 100 else "running"
            db.execute("UPDATE flight_sessions SET status=?,progress=?,telemetry_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, progress, json.dumps(telemetry), flight["id"]))
            self._record_telemetry_sample(db, mission_id, flight["id"], telemetry)
            if status == "completed": db.execute("UPDATE missions SET status='completed',status_label='已完成' WHERE id=?", (mission_id,))
            for alert in runtime_alerts(telemetry):
                self._record_runtime_event(db, mission_id, alert, telemetry)
            self._json({"session_id":flight["id"],"mission_id":mission_id,"status":status,"progress":progress,"telemetry":telemetry})

    def _record_runtime_event(self, db, mission_id, alert, telemetry):
        existing = db.execute("SELECT 1 FROM events WHERE mission_id=? AND event_type=? AND status='open'", (mission_id, alert["event_type"])).fetchone()
        if existing:
            return
        db.execute("INSERT INTO events(mission_id,event_type,severity,message,payload_json) VALUES(?,?,?,?,?)", (mission_id, alert["event_type"], alert["severity"], alert["message"], json.dumps({"telemetry": telemetry}, ensure_ascii=False)))
        db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json) VALUES(?,?,?,?)", ("runtime_alert", "mission", mission_id, json.dumps(alert, ensure_ascii=False)))

    def _record_telemetry_sample(self, db, mission_id, session_id, telemetry):
        """Persist an ordered, append-only track sample when the optional table exists."""
        if database_config()["backend"] == "postgresql":
            row = db.execute("SELECT COALESCE(MAX(sequence), 0) FROM telemetry_samples WHERE mission_id=? AND flight_session_id=?", (mission_id, session_id)).fetchone()
            sequence = int(row[0] or 0) + 1
            db.execute("INSERT INTO telemetry_samples(mission_id,flight_session_id,sequence,telemetry_json) VALUES(?,?,?,?)", (mission_id, session_id, sequence, json.dumps(telemetry, ensure_ascii=False)))
            return
        table = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='telemetry_samples'").fetchone()
        if not table:
            return
        row = db.execute("SELECT COALESCE(MAX(sequence), 0) FROM telemetry_samples WHERE mission_id=? AND flight_session_id=?", (mission_id, session_id)).fetchone()
        sequence = int(row[0] or 0) + 1
        db.execute("INSERT INTO telemetry_samples(mission_id,flight_session_id,sequence,timestamp,longitude,latitude,altitude,speed,heading,battery,link_quality,status,source,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (mission_id, session_id, sequence, telemetry["timestamp"], telemetry["longitude"], telemetry["latitude"], telemetry["altitude"], telemetry.get("speed", 0), telemetry.get("heading", 0), telemetry["battery"], telemetry.get("link_quality", 100), telemetry["status"], telemetry.get("source", "simulator"), json.dumps(telemetry, ensure_ascii=False)))

    def _telemetry_track(self, mission_id, db, session_id):
        if database_config()["backend"] == "postgresql":
            stored = db.execute("SELECT sequence,telemetry_json FROM telemetry_samples WHERE mission_id=? AND flight_session_id=? ORDER BY sequence", (mission_id, session_id)).fetchall()
            samples = []
            for row in stored:
                telemetry = json.loads(row["telemetry_json"]) if isinstance(row["telemetry_json"], str) else row["telemetry_json"]
                samples.append({"sequence": row["sequence"], **telemetry})
            return samples
        table = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='telemetry_samples'").fetchone()
        if not table:
            return []
        rows = db.execute("SELECT sequence,timestamp,longitude,latitude,altitude,speed,heading,battery,link_quality,status,source FROM telemetry_samples WHERE mission_id=? AND flight_session_id=? ORDER BY sequence", (mission_id, session_id)).fetchall()
        return [dict(row) for row in rows]

    def _ingest_telemetry(self, mission_id, payload):
        try:
            telemetry = normalize_telemetry(payload, default_source="device")
        except TelemetryError as error:
            raise ApiError(422, error.code, error.message)
        with session() as db:
            mission = db.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
            if not mission:
                raise ApiError(404, "MISSION_NOT_FOUND", "任务不存在")
            flight = db.execute("SELECT * FROM flight_sessions WHERE mission_id=? ORDER BY id DESC LIMIT 1", (mission_id,)).fetchone()
            if not flight:
                session_id = insert_returning_id(db, "INSERT INTO flight_sessions(mission_id,status,progress,telemetry_json,started_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP)", (mission_id, "running", 0, json.dumps(telemetry, ensure_ascii=False)))
            else:
                session_id = flight["id"]
                # A track is an ordered operational record. Reject stale or
                # duplicate timestamps instead of silently corrupting replay.
                latest = db.execute("SELECT timestamp FROM telemetry_samples WHERE mission_id=? AND flight_session_id=? ORDER BY sequence DESC LIMIT 1", (mission_id, session_id)).fetchone()
                if latest and latest["timestamp"]:
                    incoming = datetime.fromisoformat(telemetry["timestamp"].replace("Z", "+00:00"))
                    previous = datetime.fromisoformat(str(latest["timestamp"]).replace("Z", "+00:00"))
                    if incoming <= previous:
                        raise ApiError(409, "TELEMETRY_TIME_REVERSED", "遥测时间必须晚于上一条轨迹记录")
                db.execute("UPDATE flight_sessions SET status=?, telemetry_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", ("completed" if telemetry["status"] in {"completed", "landed"} else "running", json.dumps(telemetry, ensure_ascii=False), session_id))
            db.execute("UPDATE missions SET status=?, status_label=? WHERE id=?", ("completed" if telemetry["status"] in {"completed", "landed"} else "running", "已完成" if telemetry["status"] in {"completed", "landed"} else "运行中", mission_id))
            self._record_telemetry_sample(db, mission_id, session_id, telemetry)
            for alert in runtime_alerts(telemetry):
                self._record_runtime_event(db, mission_id, alert, telemetry)
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json) VALUES(?,?,?,?)", ("telemetry_ingest", "mission", mission_id, json.dumps({"source": telemetry["source"], "timestamp": telemetry["timestamp"]}, ensure_ascii=False)))
            self._json({"session_id": session_id, "mission_id": mission_id, "status": "completed" if telemetry["status"] in {"completed", "landed"} else "running", "telemetry": telemetry})

    def _resolve_event(self, event_id):
        with session() as db:
            event = db.execute("SELECT status FROM events WHERE id=?", (event_id,)).fetchone()
            if not event: raise ApiError(404, "EVENT_NOT_FOUND", "事件不存在")
            if event["status"] == "resolved": raise ApiError(409, "EVENT_ALREADY_RESOLVED", "事件已经处置")
            db.execute("UPDATE events SET status='resolved',resolved_at=CURRENT_TIMESTAMP WHERE id=?", (event_id,))
            self._json({"id":event_id,"status":"resolved"})

    def _mission_timeline(self, mission_id, db):
        if not db.execute("SELECT 1 FROM missions WHERE id=?", (mission_id,)).fetchone():
            raise ApiError(404, "MISSION_NOT_FOUND", "任务不存在")
        timeline = []
        for item in db.execute("SELECT action, object_type, object_id, detail_json, actor_username, created_at FROM audit_logs WHERE object_id=? ORDER BY id", (mission_id,)).fetchall():
            try:
                detail = json.loads(item["detail_json"] or "{}")
            except json.JSONDecodeError:
                detail = {"raw": item["detail_json"]}
            timeline.append({"type": "audit", "action": item["action"], "at": item["created_at"], "actor": item["actor_username"], "detail": detail})
        for item in db.execute("SELECT id, event_type, severity, message, status, created_at, resolved_at FROM events WHERE mission_id=? ORDER BY id", (mission_id,)).fetchall():
            timeline.append({"type": "event", "action": item["event_type"], "at": item["created_at"], "actor": None, "detail": {"severity": item["severity"], "message": item["message"], "status": item["status"], "resolved_at": item["resolved_at"]}})
        for item in db.execute("SELECT id, decision, risk_level, created_at FROM mission_checks WHERE mission_id=? ORDER BY id", (mission_id,)).fetchall():
            timeline.append({"type": "check", "action": "rule_check", "at": item["created_at"], "actor": None, "detail": {"decision": item["decision"], "risk_level": item["risk_level"]}})
        for item in db.execute("SELECT id, name, distance_m, risk_level, created_at FROM routes WHERE mission_id=? ORDER BY id", (mission_id,)).fetchall():
            timeline.append({"type": "route", "action": "route_created", "at": item["created_at"], "actor": None, "detail": {"route_id": item["id"], "name": item["name"], "distance_m": item["distance_m"], "risk_level": item["risk_level"]}})
        for item in db.execute("SELECT id, event_id, route_id, reason, status, actor_username, created_at, confirmed_at FROM route_replans WHERE mission_id=? ORDER BY id", (mission_id,)).fetchall():
            timeline.append({"type": "replan", "action": "replan_" + item["status"], "at": item["confirmed_at"] or item["created_at"], "actor": item["actor_username"], "detail": {"replan_id": item["id"], "event_id": item["event_id"], "route_id": item["route_id"], "reason": item["reason"]}})
        timeline.sort(key=lambda entry: entry["at"] or "", reverse=True)
        self._json({"mission_id": mission_id, "timeline": timeline})

    def _route_hard_conflicts(self, db, points):
        conflicts = []
        for layer in db.execute("SELECT * FROM layers WHERE status='published' AND level='hard'").fetchall():
            geometry = json.loads(layer["geometry_json"])
            if any(segment_intersects_polygon(tuple(left[:2]), tuple(right[:2]), geometry) for left, right in zip(points, points[1:])):
                conflicts.append(layer["name"])
        return conflicts

    def _propose_replan(self, mission_id, payload, actor_username):
        supported = {"deviation", "low_battery", "link_loss", "temporary_restriction"}
        with session() as db:
            mission = db.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
            if not mission:
                raise ApiError(404, "MISSION_NOT_FOUND", "任务不存在")
            event_id = payload.get("event_id")
            if event_id:
                event = db.execute("SELECT * FROM events WHERE id=? AND mission_id=?", (event_id, mission_id)).fetchone()
            else:
                event = db.execute("SELECT * FROM events WHERE mission_id=? AND status='open' ORDER BY id DESC LIMIT 1", (mission_id,)).fetchone()
            if not event:
                raise ApiError(409, "OPEN_EVENT_REQUIRED", "没有可用于重规划的未处置事件")
            if event["event_type"] not in supported:
                raise ApiError(422, "UNSUPPORTED_REPLAN_EVENT", "该事件类型暂不支持重规划")
            telemetry_row = db.execute("SELECT telemetry_json FROM flight_sessions WHERE mission_id=? ORDER BY id DESC LIMIT 1", (mission_id,)).fetchone()
            current = json.loads(telemetry_row["telemetry_json"]) if telemetry_row else {"longitude": mission["start_lng"], "latitude": mission["start_lat"], "altitude": mission["planned_altitude"]}
            start = [float(current.get("longitude", mission["start_lng"])), float(current.get("latitude", mission["start_lat"])), float(current.get("altitude", mission["planned_altitude"]))]
            destination = [mission["start_lng"], mission["start_lat"], mission["planned_altitude"]] if event["event_type"] in {"low_battery", "link_loss"} else [mission["end_lng"], mission["end_lat"], mission["planned_altitude"]]
            candidates = []
            if event["event_type"] in {"low_battery", "link_loss"}:
                candidates = [[start, destination]]
            else:
                mid_lng = (start[0] + destination[0]) / 2
                mid_lat = (start[1] + destination[1]) / 2
                candidates = [[start, [mid_lng, mid_lat + 0.006, start[2]], destination], [start, [mid_lng, mid_lat - 0.006, start[2]], destination]]
            chosen = next((points for points in candidates if not self._route_hard_conflicts(db, points)), None)
            if not chosen:
                raise ApiError(409, "NO_FEASIBLE_REPLAN", "候选重规划均穿越硬限制区，请人工处置")
            distance = sum(haversine(a[0], a[1], b[0], b[1]) for a, b in zip(chosen, chosen[1:]))
            route_id = insert_returning_id(db, "INSERT INTO routes(mission_id,name,points_json,distance_m,duration_s,risk_level) VALUES(?,?,?,?,?,?)", (mission_id, f"重规划候选-{event['event_type']}", json.dumps(chosen, ensure_ascii=False), distance, distance / 12, "medium"))
            reason = f"事件 {event['event_type']} 触发，等待人工确认"
            replan_id = insert_returning_id(db, "INSERT INTO route_replans(mission_id,event_id,route_id,reason,status) VALUES(?,?,?,?, 'proposed')", (mission_id, event["id"], route_id, reason))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json,actor_username) VALUES(?,?,?,?,?)", ("replan_propose", "mission", mission_id, json.dumps({"event_id": event["id"], "route_id": route_id, "reason": reason}, ensure_ascii=False), actor_username))
            self._json({"id": replan_id, "mission_id": mission_id, "event_id": event["id"], "route_id": route_id, "status": "proposed", "reason": reason, "points": chosen, "distance_m": round(distance, 1), "duration_s": round(distance / 12, 1)}, HTTPStatus.CREATED)

    def _confirm_replan(self, replan_id, actor_username):
        with session() as db:
            replan = db.execute("SELECT * FROM route_replans WHERE id=?", (replan_id,)).fetchone()
            if not replan:
                raise ApiError(404, "REPLAN_NOT_FOUND", "重规划方案不存在")
            if replan["status"] != "proposed":
                raise ApiError(409, "REPLAN_ALREADY_DECIDED", "该重规划方案已经处理")
            db.execute("UPDATE route_replans SET status='confirmed', actor_username=?, confirmed_at=CURRENT_TIMESTAMP WHERE id=?", (actor_username, replan_id))
            db.execute("UPDATE missions SET status='running', status_label='运行中' WHERE id=?", (replan["mission_id"],))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json,actor_username) VALUES(?,?,?,?,?)", ("replan_confirm", "mission", replan["mission_id"], json.dumps({"replan_id": replan_id, "route_id": replan["route_id"]}, ensure_ascii=False), actor_username))
            self._json({"id": replan_id, "mission_id": replan["mission_id"], "route_id": replan["route_id"], "status": "confirmed", "actor_username": actor_username})


def validate_mission(payload):
    required = ["id", "name", "vehicle_id", "route_name", "start_lng", "start_lat", "end_lng", "end_lat", "planned_altitude"]
    missing = [key for key in required if payload.get(key) in (None, "")]
    if missing:
        raise ApiError(422, "MISSING_FIELDS", "缺少字段: " + ", ".join(missing))
    if not MISSION_ID.match(str(payload["id"])):
        raise ApiError(422, "INVALID_MISSION_ID", "任务编号仅允许4至40位大写字母、数字和连字符")
    for key, minimum, maximum in (("start_lng", 105, 110), ("end_lng", 105, 110), ("start_lat", 28, 32), ("end_lat", 28, 32)):
        try:
            payload[key] = float(payload[key])
        except (TypeError, ValueError):
            raise ApiError(422, "INVALID_COORDINATE", f"{key} 必须为数字")
        if not minimum <= payload[key] <= maximum:
            raise ApiError(422, "OUT_OF_DEMO_AREA", f"{key} 超出演示区域")
    try:
        payload["planned_altitude"] = float(payload["planned_altitude"])
    except (TypeError, ValueError):
        raise ApiError(422, "INVALID_ALTITUDE", "计划高度必须为数字")
    if not 20 <= payload["planned_altitude"] <= 1200:
        raise ApiError(422, "INVALID_ALTITUDE", "计划高度必须在20至1200米之间")
    time_window_start, time_window_end = normalize_time_window(payload)
    return {**{key: payload[key] for key in required}, "time_window_start": time_window_start, "time_window_end": time_window_end}

def segment_intersects_box(a, b, box):
    minx,miny,maxx,maxy=box
    if minx <= a[0] <= maxx and miny <= a[1] <= maxy: return True
    if minx <= b[0] <= maxx and miny <= b[1] <= maxy: return True
    dx,dy=b[0]-a[0],b[1]-a[1]
    for x in (minx,maxx):
        if dx and 0 <= (x-a[0])/dx <= 1:
            y=a[1]+(x-a[0])*dy/dx
            if miny <= y <= maxy: return True
    for y in (miny,maxy):
        if dy and 0 <= (y-a[1])/dy <= 1:
            x=a[0]+(y-a[1])*dx/dy
            if minx <= x <= maxx: return True
    return False

def haversine(lon1,lat1,lon2,lat2):
    radius=6371000
    p1,p2=math.radians(lat1),math.radians(lat2)
    dp=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
    h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*radius*math.asin(math.sqrt(h))


def facility_reachability(db, mission):
    """Return explainable nearest-facility checks for both mission endpoints."""
    vehicle_id = mission["vehicle_id"]
    facilities = db.execute("SELECT * FROM facilities WHERE status='active'").fetchall()

    def nearest(lng, lat):
        candidates = []
        for row in facilities:
            compatible = json.loads(row["compatible_vehicles_json"] or "[]")
            if compatible and vehicle_id not in compatible:
                continue
            distance = haversine(float(lng), float(lat), row["longitude"], row["latitude"])
            radius = float(row["service_radius_m"] or 0)
            candidates.append((distance, row, radius))
        # Prefer a reachable facility; otherwise report the nearest blocked candidate.
        candidates.sort(key=lambda item: (item[0] > item[2], item[0]))
        if not candidates:
            return {"reachable": False, "reason": "没有兼容机型的可用设施", "facility": None}
        distance, row, radius = candidates[0]
        return {
            "reachable": distance <= radius,
            "distance_m": round(distance, 1),
            "service_radius_m": radius,
            "facility": {"facility_id": row["facility_id"], "name": row["name"], "facility_type": row["facility_type"], "status": row["status"]},
            "reason": None if distance <= radius else "最近设施超出服务半径",
        }

    return {"vehicle_id": vehicle_id, "start": nearest(mission["start_lng"], mission["start_lat"]), "end": nearest(mission["end_lng"], mission["end_lat"])}


def main():
    if PRODUCTION_MODE:
        bootstrap_password = os.environ.get("LP_BOOTSTRAP_PASSWORD", "")
        if len(bootstrap_password) < 12:
            raise RuntimeError("生产模式必须设置 LP_BOOTSTRAP_PASSWORD，且长度不少于12位")
        if DEMO_MODE:
            raise RuntimeError("生产模式禁止同时启用 DEMO_MODE")
    capabilities = database_capabilities()
    if capabilities["backend"] == "postgresql" and not capabilities["configured"]:
        raise RuntimeError(f"PostgreSQL 配置不可用: {capabilities.get('message')}")
    if capabilities["backend"] == "sqlite":
        init_db()
    if PRODUCTION_MODE:
        with session() as db:
            admin = db.execute("SELECT password_hash FROM users WHERE username='admin' AND enabled=1").fetchone()
            if not admin:
                raise RuntimeError("生产初始化未创建 admin 账户")
            if verify_password(os.environ["LP_BOOTSTRAP_PASSWORD"], admin["password_hash"])[0] and os.environ["LP_BOOTSTRAP_PASSWORD"] == "admin123":
                raise RuntimeError("生产模式禁止使用演示默认密码")
    host, port = os.environ.get("LP_HOST", "127.0.0.1"), int(os.environ.get("LP_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"梁平低空运行基础底座已启动: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
