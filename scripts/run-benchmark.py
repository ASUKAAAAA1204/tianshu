"""Run the three repeatable competition benchmark scenarios against a live server."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = ROOT / "data" / "demo" / "benchmarks"
DEFAULT_OUTPUT = ROOT / "docs" / "evidence" / "results" / "benchmark-summary.json"


class ApiFailure(RuntimeError):
    pass


def request(base_url: str, path: str, method: str = "GET", payload: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base_url.rstrip('/')}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"message": raw}
        return error.code, data
    except urllib.error.URLError as error:
        raise ApiFailure(f"无法连接 {base_url}: {error}") from error


def timed_call(base_url: str, path: str, method: str, payload: dict, token: str) -> tuple[float, int, dict]:
    started = time.perf_counter()
    status, result = request(base_url, path, method, payload, token)
    return round((time.perf_counter() - started) * 1000, 2), status, result


def mission_payload(case_id: str, mission: dict) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%H%M%S%f")[:9]
    return {"id": f"BM-{case_id.upper()}-{stamp}", **mission}


def require(status: int, result: dict, label: str) -> dict:
    if status >= 400:
        raise ApiFailure(f"{label} 失败 HTTP {status}: {result}")
    return result


def run_hard_zone(base_url: str, token: str, case: dict) -> dict:
    mission = mission_payload(case["case_id"], case["mission"])
    created = require(*timed_call(base_url, "/api/missions", "POST", mission, token)[1:], "创建硬限制场景")
    check_ms, check_status, checked = timed_call(base_url, f"/api/missions/{mission['id']}/check", "POST", {}, token)
    route_ms, route_status, planned = timed_call(base_url, f"/api/missions/{mission['id']}/routes/plan", "POST", {}, token)
    return {"case_id": case["case_id"], "mission_id": created["id"], "check_ms": check_ms, "check_status": check_status, "decision": checked.get("decision"), "hard_items": sum(1 for item in checked.get("items", []) if item.get("level") == "hard"), "route_ms": route_ms, "route_status": route_status, "route_strategy": planned.get("strategy"), "route_distance_m": planned.get("distance_m"), "traceability": planned.get("traceability") or checked.get("traceability")}


def run_multi_conflict(base_url: str, token: str, case: dict) -> dict:
    created_ids = []
    timings = []
    checks = []
    for index, mission_template in enumerate(case["missions"], start=1):
        mission = mission_payload(f"{case['case_id']}-{index}", mission_template)
        create_ms, status, created = timed_call(base_url, "/api/missions", "POST", mission, token)
        require(status, created, f"创建多任务场景-{index}")
        check_ms, check_status, checked = timed_call(base_url, f"/api/missions/{mission['id']}/check", "POST", {}, token)
        timings.append({"create_ms": create_ms, "check_ms": check_ms, "check_status": check_status})
        checks.append({"mission_id": mission["id"], "decision": checked.get("decision"), "hard_items": sum(1 for item in checked.get("items", []) if item.get("level") == "hard"), "traceability": checked.get("traceability")})
        created_ids.append(mission["id"])
    return {"case_id": case["case_id"], "mission_ids": created_ids, "timings": timings, "checks": checks, "hard_conflict_detected": any(item["hard_items"] > 0 for item in checks[1:])}


def run_low_battery(base_url: str, token: str, case: dict) -> dict:
    mission = mission_payload(case["case_id"], case["mission"])
    require(*timed_call(base_url, "/api/missions", "POST", mission, token)[1:], "创建低电量场景")
    check_ms, check_status, checked = timed_call(base_url, f"/api/missions/{mission['id']}/check", "POST", {}, token)
    require(check_status, checked, "低电量场景规则检查")
    route_ms, route_status, route = timed_call(base_url, f"/api/missions/{mission['id']}/routes/plan", "POST", {}, token)
    require(route_status, route, "低电量场景航线规划")
    start_ms, start_status, started = timed_call(base_url, f"/api/missions/{mission['id']}/flight/start", "POST", {}, token)
    require(start_status, started, "低电量场景启动飞行")
    event_ms, event_status, event = timed_call(base_url, f"/api/missions/{mission['id']}/events", "POST", {"event_type": "low_battery"}, token)
    require(event_status, event, "低电量事件注入")
    replan_ms, replan_status, replan = timed_call(base_url, f"/api/missions/{mission['id']}/replan", "POST", {"event_id": event["id"]}, token)
    require(replan_status, replan, "低电量重规划")
    return {"case_id": case["case_id"], "mission_id": mission["id"], "check_ms": check_ms, "route_ms": route_ms, "start_ms": start_ms, "event_ms": event_ms, "replan_ms": replan_ms, "replan_status": replan.get("status"), "event_id": event.get("id"), "traceability": replan.get("traceability") or route.get("traceability")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8877")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    status, health = request(args.base_url, "/api/health")
    if status >= 400:
        raise ApiFailure(f"健康检查失败 HTTP {status}: {health}")
    login_status, login = request(args.base_url, "/api/auth/login", "POST", {"username": args.username, "password": args.password})
    token = require(login_status, login, "登录").get("token")
    if not token:
        raise ApiFailure("登录响应缺少 token")
    _, bootstrap = request(args.base_url, "/api/bootstrap", token=token)
    cases = {
        "hard-zone": json.loads((BENCHMARK_DIR / "case-hard-zone.json").read_text(encoding="utf-8")),
        "multi-conflict": json.loads((BENCHMARK_DIR / "case-multi-conflict.json").read_text(encoding="utf-8")),
        "low-battery": json.loads((BENCHMARK_DIR / "case-low-battery.json").read_text(encoding="utf-8")),
    }
    results = [run_hard_zone(args.base_url, token, cases["hard-zone"]), run_multi_conflict(args.base_url, token, cases["multi-conflict"]), run_low_battery(args.base_url, token, cases["low-battery"])]
    output = {"generated_at": datetime.now(timezone.utc).isoformat(), "base_url": args.base_url, "health": health, "traceability": bootstrap.get("traceability"), "data_boundaries": bootstrap.get("data_boundaries"), "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ApiFailure as error:
        print(f"BENCHMARK_FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
