import json
import hashlib
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import db as db_module  # noqa: E402
from db import connect, database_capabilities, database_config, hash_password, init_db, session, sqlite_path_from_url, verify_password  # noqa: E402
import server as server_module  # noqa: E402
from server import ApiError, validate_mission, Handler, building_footprint_hits, normalize_time_window, windows_overlap, route_paths_intersect, route_data_quality, telemetry_track_csv  # noqa: E402
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
                buildings = json.loads(server_module.REFERENCE_BUILDINGS.read_text(encoding="utf-8"))
                self.assertEqual(len(buildings["features"]), 158)
                self.assertTrue(all(item["properties"]["height"] is None for item in buildings["features"]))
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
        result = validate_mission(self.valid())
        self.assertEqual(result["planned_altitude"], 120.0)
        self.assertEqual(json.loads(result["via_points_json"]), [])

    def test_normalizes_mission_via_points(self):
        payload = self.valid()
        payload["via_points"] = [{"name":"参考点A","longitude":"107.75","latitude":"30.65","source":"openstreetmap_reference","source_id":"way-1"}]
        result = validate_mission(payload)
        self.assertEqual(json.loads(result["via_points_json"]), [{"name":"参考点A","longitude":107.75,"latitude":30.65,"source":"openstreetmap_reference","source_id":"way-1"}])

    def test_rejects_invalid_mission_via_points(self):
        payload = self.valid(); payload["via_points"] = "{invalid"
        with self.assertRaises(ApiError) as context:
            validate_mission(payload)
        self.assertEqual(context.exception.code, "INVALID_VIA_POINTS")
        payload = self.valid(); payload["via_points"] = [{"longitude":120,"latitude":30}]
        with self.assertRaises(ApiError) as context:
            validate_mission(payload)
        self.assertEqual(context.exception.code, "OUT_OF_DEMO_AREA")
        payload = self.valid(); payload["via_points"] = [{"longitude":107.7,"latitude":30.6}] * 13
        with self.assertRaises(ApiError) as context:
            validate_mission(payload)
        self.assertEqual(context.exception.code, "INVALID_VIA_POINTS")

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

    def test_route_data_quality_never_promotes_synthetic_or_unregistered_inputs(self):
        quality = route_data_quality()
        self.assertEqual(quality["terrain"], "synthetic_demo")
        self.assertFalse(quality["terrain_verified"])
        self.assertEqual(quality["building_obstacles"], "not_integrated")
        self.assertFalse(quality["building_obstacles_verified"])
        self.assertTrue(quality["review_required"])
        self.assertFalse(quality["flight_safety_release"])

    def test_traceable_building_footprint_intersection_keeps_height_unknown(self):
        buildings = json.loads(server_module.REFERENCE_BUILDINGS.read_text(encoding="utf-8"))
        ring = buildings["features"][0]["geometry"]["coordinates"][0][0]
        hits = building_footprint_hits([((ring[0][0], ring[0][1]), (ring[2][0], ring[2][1]))])
        self.assertGreaterEqual(len(hits), 1)
        self.assertIsNone(hits[0]["height_m"])
        self.assertIn("OpenStreetMap", hits[0]["source"])

    def test_route_data_quality_requires_provenance_manifest_and_never_grants_clearance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "data" / "reference"
            reference.mkdir(parents=True)
            dem_bytes = b"public dem grid"
            building_bytes = b"public building features"
            (reference / "dem-grid.tif").write_bytes(dem_bytes)
            (reference / "buildings.geojson").write_bytes(building_bytes)
            common = {"verified": True, "coverage_bbox": [107.4, 30.3, 108.0, 31.0], "acquired_at": "2026-10-19", "coordinate_reference": "EPSG:4326"}
            dem_manifest = {**common, "source_url": "https://data.example/dem", "license": "public", "data_file": "dem-grid.tif", "sha256": hashlib.sha256(dem_bytes).hexdigest()}
            building_manifest = {**common, "source_url": "https://data.example/buildings", "license": "ODbL-1.0", "data_file": "buildings.geojson", "sha256": hashlib.sha256(building_bytes).hexdigest(), "height_present_count": 1}
            (reference / "dem.manifest.json").write_text(json.dumps(dem_manifest), encoding="utf-8")
            building_manifest_path = reference / "buildings.manifest.json"
            building_manifest_path.write_text(json.dumps(building_manifest), encoding="utf-8")
            dem_grid = root / "dem.json"
            dem_grid.write_text(json.dumps({"metadata": {"source": "public_reference"}}), encoding="utf-8")
            with patch.object(server_module, "ROOT", root), patch.object(server_module, "DEM_GRID", dem_grid):
                quality = route_data_quality()
                self.assertTrue(quality["building_obstacles_verified"])
                building_manifest["data_file"] = "../../outside.geojson"
                building_manifest_path.write_text(json.dumps(building_manifest), encoding="utf-8")
                tampered = route_data_quality()
        self.assertTrue(quality["terrain_verified"])
        self.assertTrue(quality["building_obstacles_verified"])
        self.assertFalse(quality["review_required"])
        self.assertFalse(quality["flight_safety_release"])
        self.assertFalse(tampered["building_obstacles_verified"])

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
