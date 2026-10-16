"""短时商用 soak：并发读取平台状态并高频写入标准遥测。"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import statistics
import time
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener


def request_json(opener, base_url: str, path: str, *, method: str = "GET", payload=None):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    started = time.perf_counter()
    try:
        with opener.open(Request(base_url.rstrip("/") + path, data=body, headers=headers, method=method), timeout=10) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8")) if raw else {}, time.perf_counter() - started, None
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        return getattr(error, "code", 0) or 0, {}, time.perf_counter() - started, str(error)


def login(base_url: str, password: str):
    opener = build_opener(CookieJar())
    code, payload, _, error = request_json(opener, base_url, "/api/auth/login", method="POST", payload={"username": "admin", "password": password})
    if code != 200:
        raise RuntimeError(f"login failed: {code} {payload or error}")
    return opener


def worker(base_url: str, password: str, mission_id: str, iterations: int, worker_id: int):
    opener = login(base_url, password)
    latencies = []
    errors = []
    for index in range(iterations):
        path = f"/api/missions/{mission_id}/telemetry"
        payload = {
            "longitude": 107.74 + ((worker_id + index) % 20) * 0.001,
            "latitude": 30.64 + ((worker_id + index) % 20) * 0.001,
            "altitude": 120,
            "speed": 12,
            "heading": float((worker_id * 17 + index) % 360),
            "battery": max(25, 92 - index * 0.05),
            "link_quality": 95,
            "status": "airborne",
            "source": "soak-test",
        }
        code, _, latency, error = request_json(opener, base_url, path, method="POST", payload=payload)
        latencies.append(latency)
        if code not in (200, 201):
            errors.append({"code": code, "error": error})
    return latencies, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8765")
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--password", default=os.getenv("LP_BOOTSTRAP_PASSWORD") or os.getenv("E2E_PASSWORD") or "test-only-bootstrap-2026")
    args = parser.parse_args()

    opener = login(args.base_url, args.password)
    code, bootstrap, _, error = request_json(opener, args.base_url, "/api/bootstrap")
    if code != 200:
        raise RuntimeError(f"bootstrap failed: {code} {bootstrap or error}")
    missions = bootstrap.get("missions") or []
    if not missions:
        raise RuntimeError("no mission available for telemetry soak")
    mission_id = missions[0]["id"]

    started = time.perf_counter()
    latencies = []
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(worker, args.base_url, args.password, mission_id, args.iterations, index) for index in range(max(1, args.workers))]
        for future in futures:
            worker_latencies, worker_errors = future.result()
            latencies.extend(worker_latencies)
            errors.extend(worker_errors)
    duration = time.perf_counter() - started
    ordered = sorted(latencies)
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)] if ordered else 0
    summary = {
        "mission": mission_id,
        "requests": len(latencies),
        "success": len(latencies) - len(errors),
        "errors": len(errors),
        "duration_s": round(duration, 3),
        "throughput_rps": round(len(latencies) / duration, 2) if duration else 0,
        "p50_s": round(statistics.median(latencies), 4) if latencies else 0,
        "p95_s": round(p95, 4),
        "max_s": round(max(latencies), 4) if latencies else 0,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
