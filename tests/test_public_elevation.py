import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import public_elevation  # noqa: E402
from public_elevation import ElevationProviderError, fetch_elevations, sample_route  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class PublicElevationTests(unittest.TestCase):
    def setUp(self):
        with public_elevation._CACHE_LOCK:
            public_elevation._CACHE.clear()
        public_elevation._LAST_UPSTREAM_REQUEST = 0.0

    def test_route_sampling_is_bounded_and_keeps_endpoints(self):
        points = sample_route([[107.74, 30.64], [107.78, 30.66]])
        self.assertLessEqual(len(points), 50)
        self.assertEqual(points[0], [107.74, 30.64])
        self.assertEqual(points[-1], [107.78, 30.66])
        self.assertGreater(len(points), 2)

    def test_rejects_outside_reference_area(self):
        with self.assertRaises(ElevationProviderError) as context:
            sample_route([[120.0, 30.0]])
        self.assertEqual(context.exception.code, "OUT_OF_REFERENCE_AREA")

    def test_fetch_returns_explicit_source_and_unknown_vertical_metadata(self):
        with patch("public_elevation.urlopen", return_value=FakeResponse({"elevation": [446.0, 456.0]})) as request:
            result = fetch_elevations([[107.75, 30.65], [107.76, 30.66]])
        self.assertTrue(result["available"])
        self.assertEqual([item["elevation_m"] for item in result["samples"]], [446.0, 456.0])
        self.assertEqual(result["vertical_datum"], "未由接口响应声明；不得用于跨基准净空换算")
        self.assertEqual(result["source_resolution_m"], 90)
        self.assertIn("GLO-90", result["source_resolution_note"])
        self.assertEqual(result["quality_level"], "public_reference_only")
        self.assertIn("商业部署前需核验", result["usage_terms"])
        self.assertIn("api.open-meteo.com", request.call_args.args[0].full_url)

    def test_cache_avoids_repeated_external_requests(self):
        with patch("public_elevation.urlopen", return_value=FakeResponse({"elevation": [446.0]})) as request:
            first = fetch_elevations([[107.75, 30.65]])
            second = fetch_elevations([[107.75, 30.65]])
        self.assertEqual(request.call_count, 1)
        self.assertEqual(first["samples"], second["samples"])

    def test_upstream_requests_are_throttled(self):
        with patch("public_elevation.urlopen", return_value=FakeResponse({"elevation": [446.0]})) as request, patch(
            "public_elevation.time.monotonic", return_value=10.0
        ), patch("public_elevation.time.sleep") as sleep:
            fetch_elevations([[107.75, 30.65]])
            fetch_elevations([[107.76, 30.66]])
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(1.0)

    def test_rejects_provider_shape_mismatch(self):
        with patch("public_elevation.urlopen", return_value=FakeResponse({"elevation": []})):
            with self.assertRaises(ElevationProviderError) as context:
                fetch_elevations([[107.75, 30.65]])
        self.assertEqual(context.exception.code, "INVALID_ELEVATION_RESPONSE")
