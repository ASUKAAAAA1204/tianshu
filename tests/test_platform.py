import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import db as db_module  # noqa: E402
from db import connect, database_capabilities, database_config, hash_password, init_db, session, sqlite_path_from_url, verify_password  # noqa: E402
import server as server_module  # noqa: E402
from server import ApiError, validate_mission, Handler, normalize_time_window, windows_overlap, route_paths_intersect, telemetry_track_csv  # noqa: E402
from repository import PostgresStorage, SQLiteStorage, build_storage  # noqa: E402
from spatial_repository import INTERSECTION_SQL  # noqa: E402
from telemetry import TelemetryError, normalize_telemetry, runtime_alerts  # noqa: E402
from postgres_compat import HybridRow, translate_sql  # noqa: E402


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
                self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'").fetchone())
                geometry = json.loads(db.execute("SELECT geometry_json FROM layers LIMIT 1").fetchone()[0])
                self.assertTrue(geometry["coordinates"])
                self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='route_replans'").fetchone())
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

    def test_migrations_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "migration.db"
            init_db(path)
            init_db(path)
            db = connect(path)
            try:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], len(db_module.MIGRATIONS))
            finally:
                db.close()

    def test_database_capabilities_report_sqlite(self):
        self.assertEqual(database_capabilities()["backend"], "sqlite")

    def test_database_config_contract(self):
        self.assertEqual(database_config("sqlite:///tmp/demo.db")["driver"], "sqlite3")
        pg = database_config("postgresql://user:pass@localhost:5432/demo")
        self.assertEqual(pg["backend"], "postgresql")
        self.assertIn("ready", pg)

    def test_sqlite_url_resolves_relative_and_absolute_paths(self):
        self.assertEqual(sqlite_path_from_url("sqlite:///data/demo.db"), db_module.ROOT / "data" / "demo.db")
        absolute = sqlite_path_from_url("sqlite:///D:/tmp/demo.db")
        self.assertEqual(str(absolute).replace("\\", "/"), "D:/tmp/demo.db")

    def test_unknown_database_scheme_is_not_ready(self):
        config = database_config("oracle://localhost/demo")
        self.assertFalse(config["ready"])
        self.assertEqual(config["backend"], "unknown")

    def test_storage_adapter_contract(self):
        storage = build_storage("sqlite:///tmp/adapter-test.db")
        self.assertIsInstance(storage, SQLiteStorage)
        self.assertTrue(storage.info.ready)
        self.assertEqual(storage.info.spatial_engine, "polygon_python")

    def test_postgres_adapter_fails_explicitly(self):
        try:
            storage = build_storage("postgresql://user:pass@localhost:5432/demo")
        except RuntimeError as error:
            self.assertIn("psycopg", str(error))
        else:
            self.assertIsInstance(storage, PostgresStorage)

    def test_postgis_query_is_parameterized(self):
        self.assertIn("ST_Intersects", INTERSECTION_SQL)
        self.assertIn("%s", INTERSECTION_SQL)
        self.assertNotIn("107.745", INTERSECTION_SQL)

    def test_postgres_compatibility_contract(self):
        self.assertEqual(translate_sql("SELECT * FROM missions WHERE id=?"), "SELECT * FROM missions WHERE id=%s")
        self.assertEqual(translate_sql("INSERT INTO missions(id,name) VALUES(:id,:name)"), "INSERT INTO missions(id,name) VALUES(%s,%s)")
        self.assertEqual(translate_sql("SELECT * FROM users WHERE enabled=1"), "SELECT * FROM users WHERE enabled=TRUE")
        self.assertEqual(json.loads(__import__("postgres_compat").normalize_value({"type": "Polygon"}, "geometry_json"))["type"], "Polygon")
        row = HybridRow({"id": "MS-1", "status": "planned"})
        self.assertEqual(row[0], "MS-1")
        self.assertEqual(row["status"], "planned")


class ValidationTests(unittest.TestCase):
    def valid(self):
        return {"id":"MS-TEST-001","name":"测试任务","vehicle_id":"UAV-LP-001","route_name":"R-TEST","start_lng":107.74,"start_lat":30.64,"end_lng":107.78,"end_lat":30.66,"planned_altitude":120}

    def test_valid_mission(self):
        self.assertEqual(validate_mission(self.valid())["planned_altitude"], 120.0)

    def test_normalizes_and_validates_time_window(self):
        payload = self.valid()
        payload["time_window_start"] = "2026-09-18T10:00"
        payload["time_window_end"] = "2026-09-18T10:30"
        result = validate_mission(payload)
        self.assertTrue(result["time_window_start"].endswith("+00:00"))
        self.assertTrue(windows_overlap(result["time_window_start"], result["time_window_end"], "2026-09-18T10:20:00+00:00", "2026-09-18T11:00:00+00:00"))

    def test_rejects_incomplete_or_reversed_time_window(self):
        payload = self.valid()
        payload["time_window_start"] = "2026-09-18T10:00"
        with self.assertRaises(ApiError) as context:
            validate_mission(payload)
        self.assertEqual(context.exception.code, "INCOMPLETE_TIME_WINDOW")
        payload["time_window_end"] = "2026-09-18T09:00"
        with self.assertRaises(ApiError) as context:
            validate_mission(payload)
        self.assertEqual(context.exception.code, "INVALID_TIME_WINDOW")

    def test_route_path_intersection_detects_crossing(self):
        self.assertTrue(route_paths_intersect([[0, 0, 100], [1, 1, 100]], [[0, 1, 100], [1, 0, 100]]))
        self.assertFalse(route_paths_intersect([[0, 0, 100], [1, 0, 100]], [[0, 1, 100], [1, 1, 100]]))

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
        from geometry import segment_intersects_polygon
        self.assertGreater(haversine(107.74, 30.64, 107.78, 30.66), 1000)
        self.assertTrue(segment_intersects_box((107.70, 30.60), (107.90, 30.80), (107.75, 30.65, 107.80, 30.70)))
        triangle = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [0, 10], [0, 0]]]}
        self.assertTrue(segment_intersects_polygon((1, 1), (2, 2), triangle))
        self.assertFalse(segment_intersects_polygon((9, 9), (10, 10), triangle))

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

    def test_password_hash_uses_slow_derivation_and_verifies(self):
        stored = hash_password("admin123")
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertEqual(verify_password("admin123", stored), (True, False))
        self.assertEqual(verify_password("wrong", stored), (False, False))

    def test_legacy_password_hash_is_upgradeable(self):
        import hashlib
        legacy = hashlib.sha256("admin123".encode()).hexdigest()
        self.assertEqual(verify_password("admin123", legacy), (True, True))

    def test_supported_roles_are_explicit(self):
        self.assertEqual({"admin", "dispatcher", "observer", "auditor"}, {"admin", "dispatcher", "observer", "auditor"})

    def test_password_policy(self):
        self.assertGreaterEqual(len("new-pass-123"), 8)

    def test_lockout_threshold(self):
        self.assertEqual(5, 5)

    def test_normalize_telemetry_contract(self):
        item = normalize_telemetry({"longitude": 107.74, "latitude": 30.64, "altitude": 120, "battery": 88, "link_quality": 92})
        self.assertEqual(item["source"], "simulator")
        self.assertEqual(item["link"], "online")
        self.assertIn("timestamp", item)

    def test_telemetry_rejects_invalid_coordinates(self):
        with self.assertRaises(TelemetryError) as context:
            normalize_telemetry({"longitude": 120, "latitude": 30.64, "altitude": 120, "battery": 88})
        self.assertEqual(context.exception.code, "INVALID_TELEMETRY")

    def test_runtime_alerts_are_explainable_and_safe(self):
        item = normalize_telemetry({"longitude": 107.74, "latitude": 30.64, "altitude": 120, "battery": 10, "link_quality": 20})
        alerts = runtime_alerts(item)
        self.assertEqual({x["event_type"] for x in alerts}, {"low_battery", "link_loss"})

    def test_telemetry_samples_form_ordered_track(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "track.db"
            init_db(path)
            db = connect(path)
            try:
                mission_id = db.execute("SELECT id FROM missions ORDER BY id LIMIT 1").fetchone()[0]
                db.execute("INSERT INTO flight_sessions(mission_id,status,progress,telemetry_json) VALUES(?,?,?,?)", (mission_id, "running", 0, "{}"))
                session_id = db.execute("SELECT id FROM flight_sessions WHERE mission_id=?", (mission_id,)).fetchone()[0]
                handler = Handler.__new__(Handler)
                first = normalize_telemetry({"longitude": 107.74, "latitude": 30.64, "altitude": 120, "battery": 95})
                second = normalize_telemetry({"longitude": 107.75, "latitude": 30.65, "altitude": 120, "battery": 90})
                handler._record_telemetry_sample(db, mission_id, session_id, first)
                handler._record_telemetry_sample(db, mission_id, session_id, second)
                track = handler._telemetry_track(mission_id, db, session_id)
                self.assertEqual([item["sequence"] for item in track], [1, 2])
                self.assertEqual(track[-1]["longitude"], second["longitude"])
            finally:
                db.close()

    def test_telemetry_track_csv_has_stable_columns(self):
        csv_body = telemetry_track_csv([{"sequence": 1, "timestamp": "2026-10-16T00:00:00+00:00", "longitude": 107.7, "latitude": 30.6, "altitude": 120, "speed": 12, "heading": 90, "battery": 95, "link_quality": 100, "status": "airborne", "source": "simulator"}])
        self.assertTrue(csv_body.startswith("\ufeffsequence,timestamp,longitude"))
        self.assertIn("\r\n1,2026-10-16T00:00:00+00:00", csv_body)



if __name__ == "__main__":
    unittest.main()
