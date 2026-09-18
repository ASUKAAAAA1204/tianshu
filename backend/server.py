from __future__ import annotations

import json
import mimetypes
import os
import re
import sqlite3
import math
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from db import init_db, rows, session


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
MISSION_ID = re.compile(r"^[A-Z0-9-]{4,40}$")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


class Handler(BaseHTTPRequestHandler):
    server_version = "LiangpingLowAltitude/0.2"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def _json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, error: ApiError):
        self._json({"code": error.code, "message": error.message}, error.status)

    def _body(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(size).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, "INVALID_JSON", "请求体必须是有效的 JSON")

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
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        try:
            route = urlparse(self.path).path
            if route == "/api/health":
                self._json({"status": "ok", "service": "liangping-low-altitude-base", "version": "0.2.0"})
                return
            if route == "/api/demo/status":
                with session() as db:
                    self._json({"layers": db.execute("SELECT COUNT(*) FROM layers").fetchone()[0], "missions": db.execute("SELECT COUNT(*) FROM missions").fetchone()[0], "audit_logs": db.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]})
                return
            with session() as db:
                resources = {
                    "/api/layers": "SELECT * FROM layers ORDER BY id",
                    "/api/vehicles": "SELECT * FROM vehicles ORDER BY id",
                    "/api/missions": "SELECT * FROM missions ORDER BY created_at DESC, id DESC",
                    "/api/rules": "SELECT * FROM rules WHERE enabled=1 ORDER BY code",
                    "/api/audit-logs": "SELECT * FROM audit_logs ORDER BY id DESC LIMIT 100",
                }
                if route == "/api/bootstrap":
                    self._json({key[5:]: rows(db, query) for key, query in resources.items() if key != "/api/audit-logs"})
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
                    self._json(result)
                    return
                route_match = re.fullmatch(r"/api/missions/([^/]+)/routes", route)
                if route_match:
                    self._json(rows(db, "SELECT * FROM routes WHERE mission_id=? ORDER BY id DESC", (route_match.group(1),)))
                    return
                event_match = re.fullmatch(r"/api/missions/([^/]+)/events", route)
                if event_match:
                    self._json(rows(db, "SELECT * FROM events WHERE mission_id=? ORDER BY id DESC", (event_match.group(1),)))
                    return
                flight_match = re.fullmatch(r"/api/missions/([^/]+)/flight", route)
                if flight_match:
                    flight = db.execute("SELECT * FROM flight_sessions WHERE mission_id=? ORDER BY id DESC LIMIT 1", (flight_match.group(1),)).fetchone()
                    if not flight: raise ApiError(404, "FLIGHT_NOT_FOUND", "尚未启动模拟飞行")
                    result = dict(flight); result["telemetry"] = json.loads(result.pop("telemetry_json")); self._json(result); return
            self._file(FRONTEND / ("index.html" if route in ("/", "/index.html") else route.lstrip("/")))
        except ApiError as error:
            self._error(error)
        except Exception as error:
            self._error(ApiError(500, "INTERNAL_ERROR", f"服务处理失败: {error}"))

    def do_POST(self):  # noqa: N802
        try:
            route = urlparse(self.path).path
            if route == "/api/demo/reset":
                init_db(reset=True)
                self._json({"status":"reset","message":"演示数据已重置"})
                return
            if route == "/api/layers/import":
                self._import_layer(self._body())
                return
            start_match = re.fullmatch(r"/api/missions/([^/]+)/flight/start", route)
            event_match = re.fullmatch(r"/api/missions/([^/]+)/events", route)
            resolve_match = re.fullmatch(r"/api/events/(\d+)/resolve", route)
            tick_match = re.fullmatch(r"/api/missions/([^/]+)/flight/tick", route)
            if start_match:
                self._start_flight(start_match.group(1)); return
            if event_match:
                self._inject_event(event_match.group(1), self._body()); return
            if resolve_match:
                self._resolve_event(int(resolve_match.group(1))); return
            if tick_match:
                self._tick_flight(tick_match.group(1), self._body()); return
            publish_match = re.fullmatch(r"/api/layers/(\d+)/(publish|disable)", route)
            if publish_match:
                self._set_layer_status(int(publish_match.group(1)), publish_match.group(2))
                return
            if route != "/api/missions":
                check_match = re.fullmatch(r"/api/missions/([^/]+)/check", route)
                plan_match = re.fullmatch(r"/api/missions/([^/]+)/routes/plan", route)
                if check_match:
                    self._check_mission(check_match.group(1))
                    return
                if plan_match:
                    self._plan_route(plan_match.group(1))
                    return
                raise ApiError(404, "NOT_FOUND", "接口不存在")
            payload = validate_mission(self._body())
            with session() as db:
                if not db.execute("SELECT 1 FROM vehicles WHERE id=?", (payload["vehicle_id"],)).fetchone():
                    raise ApiError(422, "VEHICLE_NOT_FOUND", "所选飞行器不存在")
                try:
                    db.execute(
                        """INSERT INTO missions(id,name,vehicle_id,route_name,start_lng,start_lat,end_lng,end_lat,planned_altitude,status,status_label)
                        VALUES(:id,:name,:vehicle_id,:route_name,:start_lng,:start_lat,:end_lng,:end_lat,:planned_altitude,'planned','已计划')""",
                        payload,
                    )
                except sqlite3.IntegrityError:
                    raise ApiError(409, "MISSION_EXISTS", "任务编号已经存在")
                db.execute(
                    "INSERT INTO audit_logs(action,object_type,object_id,detail_json) VALUES(?,?,?,?)",
                    ("create", "mission", payload["id"], json.dumps(payload, ensure_ascii=False)),
                )
            self._json({**payload, "status": "planned", "status_label": "已计划"}, HTTPStatus.CREATED)
        except ApiError as error:
            self._error(error)
        except Exception as error:
            self._error(ApiError(500, "INTERNAL_ERROR", f"服务处理失败: {error}"))

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
            cur = db.execute("INSERT INTO layers(name,layer_type,level,geometry_json,status,source) VALUES(?,?,?,?,?,?)", (name, layer_type, level, json.dumps(payload["features"][0]["geometry"], ensure_ascii=False), "draft", "import"))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json) VALUES(?,?,?,?)", ("import", "layer", str(cur.lastrowid), json.dumps({"name":name}, ensure_ascii=False)))
            self._json({"id":cur.lastrowid,"name":name,"status":"draft","message":"图层校验通过，等待发布"}, HTTPStatus.CREATED)

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
                ring = geometry.get("coordinates", [[]])[0]
                if not ring: continue
                lngs, lats = [p[0] for p in ring], [p[1] for p in ring]
                if segment_intersects_box(start, end, (min(lngs), min(lats), max(lngs), max(lats))):
                    level = "hard" if layer["level"] == "hard" else "soft"
                    items.append({"rule_code":"R-001" if level == "hard" else "R-003","level":level,"message":f"航线穿越{layer['name']}","action":"调整航线" if level == "hard" else "人工确认后继续"})
            decision = "blocked" if any(x["level"] == "hard" for x in items) else ("warning" if items else "pass")
            risk = "high" if decision == "blocked" else ("medium" if items else "low")
            db.execute("INSERT INTO mission_checks(mission_id,decision,risk_level,items_json) VALUES(?,?,?,?)", (mission_id, decision, risk, json.dumps(items, ensure_ascii=False)))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json) VALUES(?,?,?,?)", ("check", "mission", mission_id, json.dumps({"decision":decision,"risk_level":risk}, ensure_ascii=False)))
            self._json({"mission_id":mission_id,"decision":decision,"risk_level":risk,"items":items})

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
            cursor = db.execute("INSERT INTO routes(mission_id,name,points_json,distance_m,duration_s,risk_level) VALUES(?,?,?,?,?,?)", (mission_id, "主航线-直连", json.dumps(points), distance, duration, "medium" if latest["decision"] == "warning" else "low"))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json) VALUES(?,?,?,?)", ("plan", "route", str(cursor.lastrowid), json.dumps({"mission_id":mission_id}, ensure_ascii=False)))
            self._json({"id":cursor.lastrowid,"mission_id":mission_id,"name":"主航线-直连","points":points,"distance_m":round(distance,1),"duration_s":round(duration,1),"risk_level":"medium" if latest["decision"] == "warning" else "low"}, HTTPStatus.CREATED)

    def _start_flight(self, mission_id):
        with session() as db:
            mission = db.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
            if not mission: raise ApiError(404, "MISSION_NOT_FOUND", "任务不存在")
            active = db.execute("SELECT 1 FROM flight_sessions WHERE mission_id=? AND status='running'", (mission_id,)).fetchone()
            if active: raise ApiError(409, "FLIGHT_ALREADY_RUNNING", "该任务已经在模拟飞行中")
            route = db.execute("SELECT * FROM routes WHERE mission_id=? ORDER BY id DESC LIMIT 1", (mission_id,)).fetchone()
            if not route: raise ApiError(409, "ROUTE_REQUIRED", "请先生成航线")
            telemetry = {"longitude": mission["start_lng"], "latitude": mission["start_lat"], "altitude": mission["planned_altitude"], "battery": 100, "link": "online"}
            cur = db.execute("INSERT INTO flight_sessions(mission_id,status,progress,telemetry_json,started_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP)", (mission_id, "running", 0, json.dumps(telemetry)))
            db.execute("UPDATE missions SET status='running',status_label='运行中' WHERE id=?", (mission_id,))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json) VALUES(?,?,?,?)", ("flight_start", "mission", mission_id, json.dumps(telemetry, ensure_ascii=False)))
            self._json({"session_id":cur.lastrowid,"mission_id":mission_id,"status":"running","progress":0,"telemetry":telemetry}, HTTPStatus.CREATED)

    def _inject_event(self, mission_id, payload):
        allowed = {"deviation":("warning","发生航线偏航"),"low_battery":("critical","飞行器电量不足"),"link_loss":("critical","飞行器链路中断"),"temporary_restriction":("critical","前方出现临时限制区")}
        event_type = payload.get("event_type")
        if event_type not in allowed: raise ApiError(422, "INVALID_EVENT_TYPE", "不支持的事件类型")
        with session() as db:
            if not db.execute("SELECT 1 FROM missions WHERE id=?", (mission_id,)).fetchone(): raise ApiError(404, "MISSION_NOT_FOUND", "任务不存在")
            severity, message = allowed[event_type]
            cur = db.execute("INSERT INTO events(mission_id,event_type,severity,message,payload_json) VALUES(?,?,?,?,?)", (mission_id,event_type,severity,message,json.dumps(payload,ensure_ascii=False)))
            db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json) VALUES(?,?,?,?)", ("event", "mission", mission_id, json.dumps(payload, ensure_ascii=False)))
            self._json({"id":cur.lastrowid,"mission_id":mission_id,"event_type":event_type,"severity":severity,"message":message,"status":"open"}, HTTPStatus.CREATED)

    def _tick_flight(self, mission_id, payload):
        step = float(payload.get("step", 10))
        if not 1 <= step <= 50: raise ApiError(422, "INVALID_STEP", "推进步长必须在1至50之间")
        with session() as db:
            flight = db.execute("SELECT * FROM flight_sessions WHERE mission_id=? ORDER BY id DESC LIMIT 1", (mission_id,)).fetchone()
            mission = db.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
            if not flight or not mission: raise ApiError(404, "FLIGHT_NOT_FOUND", "尚未启动模拟飞行")
            telemetry = json.loads(flight["telemetry_json"]); progress = min(100, flight["progress"] + step)
            ratio = progress / 100
            telemetry["longitude"] = mission["start_lng"] + (mission["end_lng"] - mission["start_lng"]) * ratio
            telemetry["latitude"] = mission["start_lat"] + (mission["end_lat"] - mission["start_lat"]) * ratio
            telemetry["battery"] = max(0, round(100 - progress * 0.35, 1))
            status = "completed" if progress >= 100 else "running"
            db.execute("UPDATE flight_sessions SET status=?,progress=?,telemetry_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, progress, json.dumps(telemetry), flight["id"]))
            if status == "completed": db.execute("UPDATE missions SET status='completed',status_label='已完成' WHERE id=?", (mission_id,))
            self._json({"session_id":flight["id"],"mission_id":mission_id,"status":status,"progress":progress,"telemetry":telemetry})

    def _resolve_event(self, event_id):
        with session() as db:
            event = db.execute("SELECT status FROM events WHERE id=?", (event_id,)).fetchone()
            if not event: raise ApiError(404, "EVENT_NOT_FOUND", "事件不存在")
            if event["status"] == "resolved": raise ApiError(409, "EVENT_ALREADY_RESOLVED", "事件已经处置")
            db.execute("UPDATE events SET status='resolved',resolved_at=CURRENT_TIMESTAMP WHERE id=?", (event_id,))
            self._json({"id":event_id,"status":"resolved"})


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
    return {key: payload[key] for key in required}

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


def main():
    init_db()
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
