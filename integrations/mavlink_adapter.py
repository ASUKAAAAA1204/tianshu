"""Read-only ArduPilot MAVLink adapter for the Liangping telemetry API.

This adapter never sends MAVLink commands. It converts inbound telemetry into
the platform's normalized JSON contract and posts it to the controlled demo
endpoint. Real device credentials and flight-control actions are deliberately
out of scope for this first phase.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def telemetry_from_messages(messages: dict[str, Any], *, vehicle_id: str, sequence: int) -> dict[str, Any]:
    """Map selected pymavlink message dictionaries to the platform contract."""
    position = messages.get("GLOBAL_POSITION_INT") or {}
    hud = messages.get("VFR_HUD") or {}
    battery = messages.get("SYS_STATUS") or {}
    heartbeat = messages.get("HEARTBEAT") or {}
    gps = messages.get("GPS_RAW_INT") or {}
    lat = float(position.get("lat", 0)) / 1e7
    lon = float(position.get("lon", 0)) / 1e7
    relative_alt = position.get("relative_alt")
    altitude = float(relative_alt if relative_alt is not None else position.get("alt", 0)) / 1000
    status_code = int(heartbeat.get("system_status", 0) or 0)
    armed = bool(int(heartbeat.get("base_mode", 0) or 0) & 128)
    status = "airborne" if armed and altitude > 1 else "ready"
    if status_code == 4 and not armed:
        status = "completed"
    battery_remaining = battery.get("battery_remaining", 100)
    link_quality = float(messages.get("link_quality", 100))
    if int(gps.get("fix_type", 3) or 0) < 2:
        link_quality = min(link_quality, 20)
    return {
        "vehicle_id": vehicle_id,
        "timestamp": _now(),
        "longitude": lon,
        "latitude": lat,
        "altitude": altitude,
        "speed": float(hud.get("groundspeed", 0) or 0),
        "heading": float(hud.get("heading", position.get("hdg", 0) / 100) or 0),
        "battery": max(0, float(battery_remaining if battery_remaining is not None else 100)),
        "link_quality": link_quality,
        "status": status,
        "source": "sitl-mavlink",
        "coordinate_system": "WGS84",
        "altitude_reference": "relative_to_home",
        "sequence": sequence,
    }


class PlatformClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.token: str | None = None

    def login(self) -> None:
        body = json.dumps({"username": self.username, "password": self.password}).encode()
        request = urllib.request.Request(f"{self.base_url}/api/auth/login", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            self.token = json.loads(response.read())[
                "token"
            ]

    def post_telemetry(self, mission_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.token:
            self.login()
        body = json.dumps(payload, ensure_ascii=False).encode()
        request = urllib.request.Request(
            f"{self.base_url}/api/missions/{mission_id}/telemetry",
            body,
            {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())


def run_fixture(client: PlatformClient, mission_id: str, vehicle_id: str) -> None:
    """Send one deterministic sample for adapter/platform smoke testing."""
    sample = telemetry_from_messages(
        {
            "GLOBAL_POSITION_INT": {"lat": 306460000, "lon": 1077580000, "relative_alt": 120000, "hdg": 9000},
            "VFR_HUD": {"groundspeed": 12.5, "heading": 90},
            "SYS_STATUS": {"battery_remaining": 86},
            "HEARTBEAT": {"base_mode": 128, "system_status": 4},
            "GPS_RAW_INT": {"fix_type": 3},
        },
        vehicle_id=vehicle_id,
        sequence=1,
    )
    print(json.dumps(client.post_telemetry(mission_id, sample), ensure_ascii=False))


def run_udp(client: PlatformClient, mission_id: str, vehicle_id: str, connection: str) -> None:
    from pymavlink import mavutil

    link = mavutil.mavlink_connection(connection)
    messages: dict[str, Any] = {}
    sequence = 0
    while True:
        message = link.recv_match(blocking=True, timeout=5)
        if message is None:
            print("MAVLink timeout: no message in 5s", flush=True)
            continue
        messages[message.get_type()] = message.to_dict()
        if "GLOBAL_POSITION_INT" not in messages or "HEARTBEAT" not in messages:
            continue
        sequence += 1
        payload = telemetry_from_messages(messages, vehicle_id=vehicle_id, sequence=sequence)
        try:
            print(json.dumps(client.post_telemetry(mission_id, payload), ensure_ascii=False), flush=True)
        except urllib.error.URLError as error:
            print(f"platform post failed: {error}; retrying", flush=True)
            time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only ArduPilot SITL to Liangping telemetry adapter")
    parser.add_argument("--mission-id", default=os.getenv("LP_MISSION_ID", "MS-20260915-001"))
    parser.add_argument("--vehicle-id", default=os.getenv("LP_VEHICLE_ID", "UAV-SITL-001"))
    parser.add_argument("--platform-url", default=os.getenv("LP_PLATFORM_URL", "http://127.0.0.1:8765"))
    parser.add_argument("--username", default=os.getenv("LP_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("LP_PASSWORD", "admin123"))
    parser.add_argument("--connection", default=os.getenv("MAVLINK_CONNECTION", "udp:127.0.0.1:14550"))
    parser.add_argument("--fixture", action="store_true", help="send one deterministic sample instead of listening to UDP")
    args = parser.parse_args()
    client = PlatformClient(args.platform_url, args.username, args.password)
    run_fixture(client, args.mission_id, args.vehicle_id) if args.fixture else run_udp(client, args.mission_id, args.vehicle_id, args.connection)


if __name__ == "__main__":
    main()
