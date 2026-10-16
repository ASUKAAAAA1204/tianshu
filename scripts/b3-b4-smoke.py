"""B3/B4 API smoke: mission lifecycle, validation, time window and rule outcomes."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


BASE = os.environ.get("LP_SMOKE_BASE", "http://127.0.0.1:8765")


def request(path: str, method: str = "GET", payload=None, token: str | None = None):
    body = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode())


def assert_status(actual, expected, label):
    assert actual == expected, f"{label}: expected {expected}, got {actual}"


def main():
    status, login = request("/api/auth/login", "POST", {"username": "admin", "password": "admin123"})
    assert_status(status, 200, "admin login")
    token = login["token"]
    suffix = str(int(time.time()))[-6:]
    mission_id = f"MS-B34-{suffix}"
    payload = {
        "id": mission_id,
        "name": "B3B4 API smoke",
        "vehicle_id": "UAV-LP-001",
        "route_name": "R-B34-SMOKE",
        "start_lng": 107.700,
        "start_lat": 30.700,
        "end_lng": 107.750,
        "end_lat": 30.720,
        "planned_altitude": 120,
        "time_window_start": "2026-10-15T10:00:00+08:00",
        "time_window_end": "2026-10-15T11:00:00+08:00",
    }
    status, created = request("/api/missions", "POST", payload, token)
    assert_status(status, 201, "mission create")
    assert created["time_window_start"] and created["time_window_end"]

    status, detail = request(f"/api/missions/{mission_id}", token=token)
    assert_status(status, 200, "mission detail")
    assert detail["time_window_start"] and detail["time_window_end"]

    status, checked = request(f"/api/missions/{mission_id}/check", "POST", {}, token)
    assert_status(status, 200, "soft rule check")
    assert checked["decision"] in {"pass", "warning"}

    status, planned = request(f"/api/missions/{mission_id}/routes/plan", "POST", {}, token)
    assert_status(status, 201, "route plan")
    assert planned["distance_m"] > 0
    route_id = planned["id"]
    status, adopted = request(f"/api/missions/{mission_id}/routes/{route_id}/adopt", "POST", {"reason": "business smoke"}, token)
    assert_status(status, 201, "route adopt")
    status, started = request(f"/api/missions/{mission_id}/flight/start", "POST", {}, token)
    assert_status(status, 201, "flight start")
    status, ticked = request(f"/api/missions/{mission_id}/flight/tick", "POST", {"progress": 0.5}, token)
    assert_status(status, 200, "flight tick")
    status, event = request(f"/api/missions/{mission_id}/events", "POST", {"event_type": "deviation"}, token)
    assert_status(status, 201, "event create")
    status, resolved = request(f"/api/events/{event['id']}/resolve", "POST", {}, token)
    assert_status(status, 200, "event resolve")
    status, completed = request(f"/api/missions/{mission_id}/flight/tick", "POST", {"progress": 1.0}, token)
    assert_status(status, 200, "flight complete")

    status, duplicate = request("/api/missions", "POST", payload, token)
    assert_status(status, 409, "duplicate mission")
    assert duplicate["code"] == "MISSION_EXISTS"

    invalid = dict(payload)
    invalid["id"] = "bad id"
    status, error = request("/api/missions", "POST", invalid, token)
    assert_status(status, 422, "invalid mission id")
    assert error["code"] == "INVALID_MISSION_ID"

    incomplete_window = dict(payload)
    incomplete_window["id"] = f"MS-B34-I-{suffix}"
    incomplete_window["time_window_end"] = None
    status, error = request("/api/missions", "POST", incomplete_window, token)
    assert_status(status, 422, "incomplete time window")
    assert error["code"] == "INCOMPLETE_TIME_WINDOW"

    hard_id = f"MS-B34-H-{suffix}"
    hard_payload = dict(payload, id=hard_id, start_lng=107.760, start_lat=30.660, end_lng=107.820, end_lat=30.700)
    status, _ = request("/api/missions", "POST", hard_payload, token)
    assert_status(status, 201, "hard conflict mission create")
    status, hard_check = request(f"/api/missions/{hard_id}/check", "POST", {}, token)
    assert_status(status, 200, "hard rule check")
    assert hard_check["decision"] == "blocked"
    status, blocked = request(f"/api/missions/{hard_id}/routes/plan", "POST", {}, token)
    assert_status(status, 409, "blocked route plan")
    assert blocked["code"] == "ROUTE_BLOCKED"

    request("/api/auth/logout", "POST", {}, token)
    print("B3/B4 smoke passed")
    print(json.dumps({"mission_id": mission_id, "soft_decision": checked["decision"], "hard_decision": hard_check["decision"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
