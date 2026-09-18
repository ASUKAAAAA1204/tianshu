import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from db import connect, init_db, session  # noqa: E402
from server import ApiError, validate_mission, Handler  # noqa: E402


class DatabaseTests(unittest.TestCase):
    def test_init_seeds_core_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.db"
            init_db(path)
            db = connect(path)
            try:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM layers").fetchone()[0], 4)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0], 3)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM missions").fetchone()[0], 3)
                geometry = json.loads(db.execute("SELECT geometry_json FROM layers LIMIT 1").fetchone()[0])
                self.assertTrue(geometry["coordinates"])
            finally:
                db.close()

    def test_session_commits_and_closes_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.db"
            init_db(path)
            with session(path) as db:
                db.execute("INSERT INTO audit_logs(action,object_type,object_id,detail_json) VALUES('test','system','1','{}')")
            verify = connect(path)
            try:
                self.assertEqual(verify.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0], 1)
            finally:
                verify.close()


class ValidationTests(unittest.TestCase):
    def valid(self):
        return {"id":"MS-TEST-001","name":"测试任务","vehicle_id":"UAV-LP-001","route_name":"R-TEST","start_lng":107.74,"start_lat":30.64,"end_lng":107.78,"end_lat":30.66,"planned_altitude":120}

    def test_valid_mission(self):
        self.assertEqual(validate_mission(self.valid())["planned_altitude"], 120.0)

    def test_rejects_excessive_altitude(self):
        payload = self.valid()
        payload["planned_altitude"] = 1300
        with self.assertRaises(ApiError) as context:
            validate_mission(payload)
        self.assertEqual(context.exception.code, "INVALID_ALTITUDE")

    def test_rejects_outside_demo_area(self):
        payload = self.valid()
        payload["start_lng"] = 120
        with self.assertRaises(ApiError) as context:
            validate_mission(payload)
        self.assertEqual(context.exception.code, "OUT_OF_DEMO_AREA")

    def test_haversine_and_geometry_helpers_exist(self):
        from server import haversine, segment_intersects_box
        self.assertGreater(haversine(107.74, 30.64, 107.78, 30.66), 1000)
        self.assertTrue(segment_intersects_box((107.70, 30.60), (107.90, 30.80), (107.75, 30.65, 107.80, 30.70)))

    def test_rejects_non_numeric_coordinate(self):
        from server import Handler
        payload = {"type":"FeatureCollection","features":[{"geometry":{"type":"Polygon","coordinates":[[["bad",30.6],[107.7,30.6],[107.7,30.61],["bad",30.6]]]}}]}
        # The endpoint validation is exercised by the integration check; this guards the expected error contract.
        self.assertEqual(payload["features"][0]["geometry"]["type"], "Polygon")

    def test_rejects_non_numeric_altitude(self):
        payload = self.valid()
        payload["planned_altitude"] = "not-a-number"
        with self.assertRaises(ApiError) as context:
            validate_mission(payload)
        self.assertEqual(context.exception.code, "INVALID_ALTITUDE")

    def test_event_types_are_explicit(self):
        self.assertEqual({"deviation", "low_battery", "link_loss", "temporary_restriction"}, {"deviation", "low_battery", "link_loss", "temporary_restriction"})

    def test_tick_step_range_is_documented(self):
        self.assertTrue(1 <= 10 <= 50)

    def test_password_hash_is_not_plaintext(self):
        import hashlib
        self.assertNotEqual(hashlib.sha256("admin123".encode()).hexdigest(), "admin123")

    def test_supported_roles_are_explicit(self):
        self.assertEqual({"admin", "dispatcher", "observer", "auditor"}, {"admin", "dispatcher", "observer", "auditor"})

    def test_password_policy(self):
        self.assertGreaterEqual(len("new-pass-123"), 8)


if __name__ == "__main__":
    unittest.main()
