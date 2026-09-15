from __future__ import annotations

import json
import mimetypes
import os
import re
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from db import connect, init_db, rows


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
            with connect() as db:
                resources = {
                    "/api/layers": "SELECT * FROM layers WHERE status='published' ORDER BY id",
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
            self._file(FRONTEND / ("index.html" if route in ("/", "/index.html") else route.lstrip("/")))
        except ApiError as error:
            self._error(error)
        except Exception as error:
            self._error(ApiError(500, "INTERNAL_ERROR", f"服务处理失败: {error}"))

    def do_POST(self):  # noqa: N802
        try:
            route = urlparse(self.path).path
            if route != "/api/missions":
                raise ApiError(404, "NOT_FOUND", "接口不存在")
            payload = validate_mission(self._body())
            with connect() as db:
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
    payload["planned_altitude"] = float(payload["planned_altitude"])
    if not 20 <= payload["planned_altitude"] <= 1200:
        raise ApiError(422, "INVALID_ALTITUDE", "计划高度必须在20至1200米之间")
    return {key: payload[key] for key in required}


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
