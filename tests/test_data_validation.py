import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_demo_data", ROOT / "scripts" / "validate-demo-data.py")
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class DemoDataValidationTests(unittest.TestCase):
    def test_current_demo_data_reports_explicit_boundaries(self):
        result = VALIDATOR.validate_demo_data()
        self.assertEqual(result["spatial_assets"], 62)
        self.assertEqual(result["synthetic_reference_points"], 30)
        self.assertEqual(result["synthetic_risk_points"], 24)
        self.assertEqual(result["osm_reference_features"], 780)
        self.assertEqual(result["building_reference_features"], 158)
        self.assertEqual(result["building_height_present"], 0)
        self.assertEqual(result["building_height_missing"], 158)
        self.assertEqual(result["dem_elevation_samples"], 90)
        self.assertIn("data/source/dem/N30E107.hgt.gz", result["missing_optional_sources"])
        self.assertIn("synthetic DEM", result["readiness_boundary"])

    def test_rejects_unclosed_polygon_ring(self):
        geometry = {"type": "Polygon", "coordinates": [[[107.7, 30.6], [107.8, 30.6], [107.8, 30.7], [107.7, 30.7]]]}
        with self.assertRaisesRegex(ValueError, "must be closed"):
            VALIDATOR.validate_geometry(geometry, "fixture")

    def test_rejects_invalid_wgs84_coordinates(self):
        with self.assertRaisesRegex(ValueError, "longitude out of WGS84 range"):
            VALIDATOR.validate_geometry({"type": "Point", "coordinates": [181, 30]}, "fixture")

    def test_rejects_degenerate_polygon_ring(self):
        ring = [[107.7, 30.6], [107.8, 30.6], [107.9, 30.6], [107.7, 30.6]]
        with self.assertRaisesRegex(ValueError, "zero area"):
            VALIDATOR.validate_geometry({"type": "Polygon", "coordinates": [ring]}, "fixture")

    def test_current_manifest_matches_data_files(self):
        self.assertEqual(VALIDATOR.verify_manifest(), len(VALIDATOR.DATA_FILES))

    def test_building_manifest_rejects_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "data" / "reference"
            reference.mkdir(parents=True)
            (reference / "buildings.geojson").write_text("{}", encoding="utf-8")
            manifest = {
                "verified": True, "source_url": "https://example.test/data", "license": "ODbL-1.0",
                "acquired_at": "2026-10-20T00:00:00Z", "coordinate_reference": "EPSG:4326",
                "coverage_bbox": [107.7, 30.6, 107.8, 30.7], "data_file": "buildings.geojson",
                "sha256": "0" * 64, "feature_count": 0, "height_present_count": 0, "height_missing_count": 0,
            }
            (reference / "buildings.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                VALIDATOR.validate_building_manifest(root)

    def test_building_manifest_rejects_data_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "data" / "reference"
            reference.mkdir(parents=True)
            manifest = {
                "verified": True, "source_url": "https://example.test/data", "license": "ODbL-1.0",
                "acquired_at": "2026-10-20T00:00:00Z", "coordinate_reference": "EPSG:4326",
                "coverage_bbox": [107.7, 30.6, 107.8, 30.7], "data_file": "../../outside.geojson",
                "sha256": "0" * 64, "feature_count": 0, "height_present_count": 0, "height_missing_count": 0,
            }
            (reference / "buildings.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "escapes reference directory"):
                VALIDATOR.validate_building_manifest(root)

    def test_building_manifest_rejects_features_outside_coverage(self):
        source = json.loads((ROOT / "data" / "reference" / "liangping-buildings.geojson").read_text(encoding="utf-8"))
        def shift_positions(value):
            if len(value) == 2 and all(isinstance(item, (int, float)) for item in value):
                return [value[0] + 10, value[1]]
            return [shift_positions(item) for item in value]
        source["features"][0]["geometry"]["coordinates"] = shift_positions(source["features"][0]["geometry"]["coordinates"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "data" / "reference"
            reference.mkdir(parents=True)
            data_path = reference / "buildings.geojson"
            data_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            manifest = json.loads((ROOT / "data" / "reference" / "buildings.manifest.json").read_text(encoding="utf-8"))
            manifest["data_file"] = data_path.name
            manifest["sha256"] = hashlib.sha256(data_path.read_bytes()).hexdigest()
            (reference / "buildings.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside manifest coverage_bbox"):
                VALIDATOR.validate_building_manifest(root)


if __name__ == "__main__":
    unittest.main()
