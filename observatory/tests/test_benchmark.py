"""Measurement checks without starting Docker or the live generator."""
import argparse
import importlib.util
import io
import json
import pathlib
import tempfile
import threading
import unittest
import urllib.error
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("observatory_benchmark", pathlib.Path(__file__).parents[1] / "scripts" / "benchmark.py")
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class ExportResponse(io.BytesIO):
    headers = {"Content-Type": "application/x-ndjson"}


class BenchmarkTests(unittest.TestCase):
    def test_tail_latency_and_empty_summary(self):
        self.assertEqual(benchmark.summarize(range(1, 101))["p99_ms"], 99)
        self.assertIsNone(benchmark.summarize([])["p99_ms"])

    def test_export_measures_headers_first_record_and_total_separately(self):
        body = b'\n{"id":"a","attributes":{}}\n'
        with patch.object(benchmark.urllib.request, "urlopen", return_value=ExportResponse(body)), patch.object(benchmark.time, "monotonic", side_effect=[1, 1.02, 1.03, 1.06]):
            result = benchmark.stream_export("http://example.invalid/export")
        self.assertEqual(result["count"], 1)
        self.assertAlmostEqual(result["headers_ms"], 20)
        self.assertAlmostEqual(result["first_record_ms"], 30)
        self.assertAlmostEqual(result["duration_ms"], 60)

    def test_empty_export_has_no_first_record_latency(self):
        with patch.object(benchmark.urllib.request, "urlopen", return_value=ExportResponse(b"")):
            result = benchmark.stream_export("http://example.invalid/export")
        self.assertEqual(result["count"], 0)
        self.assertIsNone(result["first_record_ms"])

    def test_mixed_probes_report_errors_and_keep_metrics_compact(self):
        lock = threading.Lock()
        enough_points = threading.Event()
        requests = []
        point_count = 0
        rejected = False
        frame = {"frame_id": "g0", "frame_kind": "galactic", "unit": "ly"}

        def request(url, payload=None, timeout=30):
            nonlocal point_count, rejected
            path = benchmark.urllib.parse.urlsplit(url).path
            with lock:
                requests.append((path, payload))
                if path.endswith('/objects') and not rejected:
                    rejected = True
                    raise urllib.error.HTTPError(url, 429, "busy", {}, None)
                if path.endswith('/points'):
                    point_count += 1
                    if point_count >= 2:
                        enough_points.set()
            if path.endswith('/api/health'): return {"status": "ok"}
            if path.endswith('/start'): return {"state": "running"}
            if path.endswith('/status'):
                self.assertTrue(enough_points.wait(3), "both readers must reach the spatial probe")
                return {"state": "finished", "stats": {"acknowledged_objects": 1, "in_flight": 0}, "process": {"cpu_seconds": 0.1}}
            if path.endswith('/receipt'): return {"stats": {"elapsed_seconds": 1, "acknowledged_objects": 1}}
            if path.endswith('/metrics'): return {"object_count": 1, "database_bytes": 10, "categories": [{"large": "tree"}], "recent_messages": []}
            if path.endswith('/types'): return {"items": []}
            if path.endswith('/frames'): return {"items": [frame]}
            if path.endswith('/points'): return {"items": [{"id": "a"}], "frame": frame}
            if path.endswith('/objects'): return {"items": [{"id": "a", "type_id": 1}], "next_cursor": None, "snapshot_max": 1}
            if path.endswith('/objects/a'): return {"object": {"id": "a"}}
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(prefix="unit", base_url="http://app.invalid", generator_url="http://generator.invalid", target_url="http://app:8000/ingest", readers=2, browse_interval=0.001, export_interval=1, points_limit=3000, warmup_seconds=0, no_exports=True, seed=73, seconds=1, batch_size=100, workers=4, profile="bursty", containers=[], output=pathlib.Path(tmp))
            with patch.object(benchmark, "json_request", side_effect=request), patch.object(benchmark, "stream_export", return_value={"count": 1, "duration_ms": 3}), patch("builtins.print"):
                report = benchmark.run_tier(args, 500, 4)
            self.assertEqual(report["report_version"], 2)
            self.assertEqual(report["config"]["seed"], 73)
            self.assertEqual(report["query_request_counts"]["list"]["http_statuses"]["429"], 1)
            self.assertGreaterEqual(report["query_latency"]["points"]["count"], 2)
            self.assertTrue(report["final_export_count_matches"])
            self.assertEqual(report["concurrent_exports"], [])
            self.assertNotIn("categories", report["metric_samples"][0])
            self.assertIn("categories", report["final_metrics"])
            self.assertTrue(report["errors"])
            self.assertTrue(list(pathlib.Path(tmp).glob('*.json')))


if __name__ == "__main__":
    unittest.main()
