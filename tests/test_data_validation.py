import importlib.util
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


if __name__ == "__main__":
    unittest.main()
