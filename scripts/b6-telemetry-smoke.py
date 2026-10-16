#!/usr/bin/env python3
"""Isolated end-to-end check for SQLite URL selection and telemetry export."""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def request(base_url: str, path: str, method: str = "GET", payload=None, token: str | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base_url + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


def json_request(base_url: str, path: str, method: str = "GET", payload=None, token: str | None = None):
    status, headers, body = request(base_url, path, method, payload, token)
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        decoded = body.decode("utf-8", errors="replace")
    return status, headers, decoded


def require(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def main() -> int:
    temp_dir = tempfile.mkdtemp(prefix="lp-b6-")
    try:
        db_path = Path(temp_dir) / "isolated-demo.db"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update({
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "LP_HOST": "127.0.0.1",
            "LP_PORT": str(port),
            "LP_ENV": "development",
            "DEMO_MODE": "false",
            "LP_BOOTSTRAP_PASSWORD": "admin123",
            "PYTHONPATH": str(ROOT / "backend"),
        })
        log = tempfile.TemporaryFile(mode="w+b")
        process = subprocess.Popen([sys.executable, str(ROOT / "backend" / "server.py")], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 30
            health = None
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    status, _, health = json_request(base_url, "/api/health")
                    if status == 200:
                        break
                except (urllib.error.URLError, TimeoutError, OSError):
                    time.sleep(0.2)
            require(process.poll() is None, "测试服务启动进程已退出")
            require(health and health["database"]["adapter"] == "sqlite", "健康检查未报告 SQLite 适配器")
            status, _, auth = json_request(base_url, "/api/auth/login", "POST", {"username": "admin", "password": "admin123"})
            require(status == 200, f"管理员登录失败: {auth}")
            token = auth["token"]
            status, _, deep = json_request(base_url, "/api/health/deep", token=token)
            require(status == 200 and deep["status"] == "ready", f"SQLite 深度健康检查失败: status={status}, body={deep}")
            status, _, bootstrap = json_request(base_url, "/api/bootstrap", token=token)
            require(status == 200 and bootstrap["vehicles"], "初始化种子数据缺失")

            mission_id = f"B6-{int(time.time())}"
            mission = {
                "id": mission_id,
                "name": "隔离遥测轨迹验收",
                "vehicle_id": bootstrap["vehicles"][0]["id"],
                "route_name": "B6-TEST",
                "start_lng": 107.69,
                "start_lat": 30.68,
                "end_lng": 107.695,
                "end_lat": 30.682,
                "planned_altitude": 120,
            }
            status, _, created = json_request(base_url, "/api/missions", "POST", mission, token)
            require(status == 201, f"创建测试任务失败: {created}")
            status, _, checked = json_request(base_url, f"/api/missions/{mission_id}/check", "POST", {}, token)
            require(status == 200 and checked["decision"] != "blocked", f"规则检查阻断测试航线: {checked}")
            status, _, route = json_request(base_url, f"/api/missions/{mission_id}/routes/plan", "POST", {}, token)
            require(status == 201, f"生成测试航线失败: {route}")
            status, _, decision = json_request(base_url, f"/api/missions/{mission_id}/routes/{route['id']}/adopt", "POST", {"reason": "B6 隔离验收采用"}, token)
            require(status == 201 and decision["decision"] == "adopted", f"航线采用决策失败: {decision}")
            status, _, decisions = json_request(base_url, f"/api/missions/{mission_id}/route-decisions", token=token)
            require(status == 200 and decisions[0]["decision"] == "adopted", "航线决策记录未持久化")
            status, _, started = json_request(base_url, f"/api/missions/{mission_id}/flight/start", "POST", {}, token)
            require(status == 201, f"启动模拟飞行失败: {started}")
            for _ in range(4):
                status, _, tick = json_request(base_url, f"/api/missions/{mission_id}/flight/tick", "POST", {"step": 25}, token)
                require(status == 200, f"模拟飞行推进失败: {tick}")

            status, _, track = json_request(base_url, f"/api/missions/{mission_id}/telemetry/track", token=token)
            require(status == 200 and len(track["samples"]) == 5, f"轨迹采样数不正确: {track}")
            require([sample["sequence"] for sample in track["samples"]] == [1, 2, 3, 4, 5], "轨迹顺序或序号不连续")
            stale = dict(track["samples"][0]); stale.update({"battery": 80, "source": "device"})
            status, _, stale_result = json_request(base_url, f"/api/missions/{mission_id}/telemetry", "POST", stale, token)
            require(status == 409 and stale_result["code"] == "TELEMETRY_TIME_REVERSED", "旧时间遥测未被拒绝")
            status, headers, csv_bytes = request(base_url, f"/api/missions/{mission_id}/telemetry/track?format=csv", token=token)
            csv_text = csv_bytes.decode("utf-8-sig")
            require(status == 200 and headers.get_content_type() == "text/csv", "CSV轨迹导出响应头错误")
            require(f'{mission_id}-track.csv' in headers.get("Content-Disposition", ""), "CSV文件名未包含任务编号")
            require(csv_text.count("\r\n") == 6 and "sequence,timestamp,longitude" in csv_text, "CSV轨迹内容或行数不正确")
            status, _, bad_format = json_request(base_url, f"/api/missions/{mission_id}/telemetry/track?format=xml", token=token)
            require(status == 422 and bad_format["code"] == "INVALID_TRACK_FORMAT", "非法轨迹导出格式未被拒绝")

            db = sqlite3.connect(db_path)
            try:
                persisted_samples = db.execute("SELECT COUNT(*) FROM telemetry_samples").fetchone()[0]
                persisted_mission = db.execute("SELECT COUNT(*) FROM missions WHERE id=?", (mission_id,)).fetchone()[0]
                files = [str(item) for item in db_path.parent.glob("**/*")]
                require(persisted_samples == 5 and persisted_mission == 1, f"接口与当前 DATABASE_URL 文件不一致: samples={persisted_samples}, mission={persisted_mission}, path={db_path}, files={files}")
            finally:
                db.close()

            print(json.dumps({"status": "passed", "db_isolated": True, "mission_id": mission_id, "track_samples": 5, "csv_rows": 5, "deep_health": deep["status"]}, ensure_ascii=False))
        finally:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            log.seek(0)
            output = log.read().decode("utf-8", errors="replace")
            log.close()
            if process.returncode not in (0, -15, 1, 143):
                print(output[-4000:], file=sys.stderr)
        return 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"B6 telemetry smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1)
