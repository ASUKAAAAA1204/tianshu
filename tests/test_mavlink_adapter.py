import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integrations.mavlink_adapter import telemetry_from_messages  # noqa: E402


class MavlinkAdapterTests(unittest.TestCase):
    def test_maps_position_and_flight_state(self):
        payload = telemetry_from_messages({
            "GLOBAL_POSITION_INT": {"lat": 306460000, "lon": 1077580000, "relative_alt": 120000, "hdg": 9000},
            "VFR_HUD": {"groundspeed": 12.5, "heading": 90},
            "SYS_STATUS": {"battery_remaining": 86},
            "HEARTBEAT": {"base_mode": 128, "system_status": 4},
            "GPS_RAW_INT": {"fix_type": 3},
        }, vehicle_id="UAV-SITL-001", sequence=7)
        self.assertEqual(payload["vehicle_id"], "UAV-SITL-001")
        self.assertAlmostEqual(payload["longitude"], 107.758)
        self.assertAlmostEqual(payload["latitude"], 30.646)
        self.assertEqual(payload["altitude"], 120.0)
        self.assertEqual(payload["status"], "airborne")
        self.assertEqual(payload["sequence"], 7)
        self.assertEqual(payload["source"], "sitl-mavlink")

    def test_invalid_gps_degrades_link_quality(self):
        payload = telemetry_from_messages({
            "GLOBAL_POSITION_INT": {"lat": 306460000, "lon": 1077580000, "relative_alt": 0},
            "HEARTBEAT": {"base_mode": 0, "system_status": 3},
            "GPS_RAW_INT": {"fix_type": 1},
        }, vehicle_id="UAV-SITL-001", sequence=8)
        self.assertLessEqual(payload["link_quality"], 20)
        self.assertEqual(payload["status"], "ready")


if __name__ == "__main__":
    unittest.main()
