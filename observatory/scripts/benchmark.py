#!/usr/bin/env python3
"""Real-generator mixed workload: concurrent browsing, details and bounded NDJSON exports.

No third-party Python dependencies. Run with the Compose app and generator up.
Each tier is a fresh isolated run. The complete receipt and request errors are saved.
"""

import argparse
import datetime as dt
import hashlib
import json
import math
import pathlib
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


def json_request(url, payload=None, timeout=30):
    raw = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=raw, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.load(res)


def percentile(values, q):
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(q * len(values)) - 1)]


def summarize(values):
    return {
        "count": len(values),
        "mean_ms": statistics.mean(values) if values else None,
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "max_ms": max(values) if values else None,
    }


def stream_export(url):
    start = time.monotonic()
    count = byte_count = 0
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=120) as response:
        headers = dict(response.headers)
        for line in response:
            if not line.strip():
                continue
            obj = json.loads(line)
            assert isinstance(obj.get("id"), str), "export record lacks string id"
            assert isinstance(obj.get("attributes"), dict), "export lost attributes"
            count += 1
            byte_count += len(line)
            digest.update(line)
    return {
        "count": count,
        "bytes": byte_count,
        "duration_ms": (time.monotonic() - start) * 1000,
        "sha256": digest.hexdigest(),
        "headers": headers,
    }


def run_tier(args, rate, index):
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    test_id = f"{args.prefix}-{rate}-{stamp}-{index}"
    run_url = (
        args.base_url.rstrip("/") + "/api/runs/" + urllib.parse.quote(test_id, safe="")
    )
    stop = threading.Event()
    latencies = {"list": [], "detail": [], "metrics": []}
    errors = []
    exports = []
    metric_samples = []
    resource_samples = []
    start = time.monotonic()

    def browse():
        cursor = None
        snapshot = None
        while not stop.is_set():
            query = {"limit": 50}
            if cursor:
                query.update(cursor=cursor, snapshot_max=snapshot)
            try:
                t = time.monotonic()
                page = json_request(
                    run_url + "/objects?" + urllib.parse.urlencode(query)
                )
                latencies["list"].append((time.monotonic() - t) * 1000)
                cursor = page.get("next_cursor")
                snapshot = page.get("snapshot_max")
                if page["items"]:
                    t = time.monotonic()
                    detail = json_request(
                        run_url
                        + "/objects/"
                        + urllib.parse.quote(page["items"][0]["id"], safe="")
                    )
                    assert detail["object"]["id"] == page["items"][0]["id"]
                    latencies["detail"].append((time.monotonic() - t) * 1000)
            except (OSError, ValueError, AssertionError, KeyError, TypeError) as exc:
                if (
                    isinstance(exc, urllib.error.HTTPError)
                    and exc.code == 404
                    and time.monotonic() - start < 5
                ):
                    pass
                else:
                    errors.append(
                        {
                            "kind": "browse",
                            "error": repr(exc),
                            "at_s": time.monotonic() - start,
                        }
                    )
            stop.wait(0.15)

    def export_loop():
        stop.wait(4)
        while not stop.is_set():
            try:
                result = stream_export(run_url + "/export.ndjson")
                result["at_s"] = time.monotonic() - start
                exports.append(result)
            except (OSError, ValueError, AssertionError, KeyError, TypeError) as exc:
                errors.append(
                    {
                        "kind": "export",
                        "error": repr(exc),
                        "at_s": time.monotonic() - start,
                    }
                )
            stop.wait(args.export_interval)

    def metrics_loop():
        while not stop.is_set():
            try:
                t = time.monotonic()
                m = json_request(run_url + "/metrics")
                latencies["metrics"].append((time.monotonic() - t) * 1000)
                metric_samples.append({"at_s": time.monotonic() - start, **m})
            except (OSError, ValueError, AssertionError, KeyError, TypeError) as exc:
                if not (isinstance(exc, urllib.error.HTTPError) and exc.code == 404):
                    errors.append(
                        {
                            "kind": "metrics",
                            "error": repr(exc),
                            "at_s": time.monotonic() - start,
                        }
                    )
            stop.wait(2)

    def resources_loop():
        while not stop.is_set():
            try:
                cmd = [
                    "docker",
                    "stats",
                    "--no-stream",
                    "--format",
                    "{{json .}}",
                    *args.containers,
                ]
                output = subprocess.check_output(cmd, text=True, timeout=10)
                resource_samples.append(
                    {
                        "at_s": time.monotonic() - start,
                        "containers": [
                            json.loads(s) for s in output.splitlines() if s.strip()
                        ],
                    }
                )
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                errors.append(
                    {
                        "kind": "docker_stats",
                        "error": repr(exc),
                        "at_s": time.monotonic() - start,
                    }
                )
            stop.wait(2)

    config = {
        "workload": "objects",
        "target_url": args.target_url,
        "test_id": test_id,
        "seed": 42 + index,
        "batch_size": args.batch_size,
        "workers": args.workers,
        "objects_per_second": rate,
        "rate_profile": args.profile,
        "ramp_seconds": min(5, args.seconds // 5),
        "duration_seconds": args.seconds,
        "max_batches": max(
            20000, math.ceil(rate * args.seconds / args.batch_size * 2) + 1000
        ),
        "retries": 2,
        "objects": {"scenario": "evolving", "tree_every_batches": 20},
    }
    health = json_request(args.base_url.rstrip("/") + "/api/health")
    start_response = json_request(args.generator_url.rstrip("/") + "/start", config)
    threads = [
        threading.Thread(target=f, daemon=True)
        for f in (browse, export_loop, metrics_loop)
    ]
    if args.containers:
        threads.append(threading.Thread(target=resources_loop, daemon=True))
    for t in threads:
        t.start()
    last_status = None
    try:
        deadline = time.monotonic() + args.seconds + 120
        while time.monotonic() < deadline:
            last_status = json_request(args.generator_url.rstrip("/") + "/status")
            if last_status.get("state") == "finished":
                break
            time.sleep(0.5)
        else:
            json_request(args.generator_url.rstrip("/") + "/stop", {})
            raise TimeoutError(
                "Generator did not finish within configured duration + 120s"
            )
        receipt = json_request(args.generator_url.rstrip("/") + "/receipt")
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=125)
    duration = time.monotonic() - start
    metrics = json_request(run_url + "/metrics")
    final_export = stream_export(run_url + "/export.ndjson")
    count_matches = final_export["count"] == metrics["object_count"]
    if not count_matches:
        errors.append(
            {
                "kind": "final_export_count",
                "actual": final_export["count"],
                "expected": metrics["object_count"],
            }
        )
    stats = receipt.get("stats", {})
    generator_elapsed = stats.get("elapsed_seconds", duration)
    report = {
        "test_id": test_id,
        "config": config,
        "health": health,
        "started_at_utc": stamp,
        "wall_seconds_including_probe_drain": duration,
        "generator_elapsed_seconds": generator_elapsed,
        "start_response": start_response,
        "last_status": last_status,
        "receipt": receipt,
        "final_metrics": metrics,
        "generator_acknowledged_objects_per_second": stats.get(
            "acknowledged_objects", 0
        )
        / generator_elapsed,
        "applied_objects_per_generator_second": metrics["object_count"]
        / generator_elapsed,
        "query_latency": {k: summarize(v) for k, v in latencies.items()},
        "concurrent_exports": exports,
        "final_export": final_export,
        "final_export_count_matches": count_matches,
        "errors": errors,
        "metric_samples": metric_samples,
        "resource_samples": resource_samples,
        "notes": [
            "Target rate is not measured throughput. Generator ACK includes only main stream; injections have separate receipt counters.",
            "Applied object count excludes duplicates and whole-message quarantines.",
            "Synchronous ingestion has no post-ACK processing backlog; requests still in flight are in generator receipt.",
            "Mixed queries and exports originate outside the application container; backend resources use docker stats.",
        ],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / (test_id + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {
                "report": str(path),
                "test_id": test_id,
                "objects": metrics["object_count"],
                "ack_per_s": report["generator_acknowledged_objects_per_second"],
                "applied_per_s": report["applied_objects_per_generator_second"],
                "latency": report["query_latency"],
                "concurrent_exports": len(exports),
                "final_export_count_matches": count_matches,
                "errors": len(errors),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--generator-url", default="http://127.0.0.1:9001")
    p.add_argument(
        "--target-url",
        default="http://app:8000/ingest",
        help="URL visible from generator container",
    )
    p.add_argument("--rates", type=int, nargs="+", default=[500, 3000])
    p.add_argument("--seconds", type=int, default=60)
    p.add_argument("--batch-size", type=int, default=100)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--profile", default="bursty")
    p.add_argument("--export-interval", type=float, default=8)
    p.add_argument("--prefix", default="mixed")
    p.add_argument("--containers", nargs="*", default=[])
    p.add_argument(
        "--output", type=pathlib.Path, default=pathlib.Path("evidence/benchmarks")
    )
    args = p.parse_args()
    reports = [run_tier(args, rate, i) for i, rate in enumerate(args.rates)]
    if any(r["errors"] for r in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
