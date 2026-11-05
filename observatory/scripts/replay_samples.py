#!/usr/bin/env python3
"""Replay original probe samples. This is protocol validation, not a load benchmark."""

import argparse
import collections
import hashlib
import json
import pathlib
import tarfile
import time
import urllib.request
from contextlib import ExitStack


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument(
        "--samples",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parents[1]
        / "tests/fixtures/samples.tar.gz",
    )
    p.add_argument(
        "--test-id",
        default=None,
        help="Optional new run ID; object IDs remain original",
    )
    p.add_argument("--output", type=pathlib.Path)
    args = p.parse_args()
    with ExitStack() as stack:
        if args.samples.is_dir():
            read_sample = lambda name: (args.samples / name).read_bytes()
            archive = None
        else:
            archive = stack.enter_context(tarfile.open(args.samples, "r:gz"))
            read_sample = lambda name: archive.extractfile(name).read()
        manifest = json.loads(read_sample("MANIFEST.json"))
        expected = {m["file"]: m["sha256"] for m in manifest["messages"]}
        results = []
        start = time.monotonic()
        for name in sorted(expected):
            raw = read_sample(name)
            assert hashlib.sha256(raw).hexdigest() == expected[name], (
                f"Corrupt source sample: {name}"
            )
            if args.test_id:
                data = json.loads(raw)
                data["test_id"] = args.test_id
                raw = json.dumps(
                    data, ensure_ascii=False, separators=(",", ":")
                ).encode()
            req = urllib.request.Request(
                args.base_url.rstrip("/") + "/ingest",
                data=raw,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.load(response)
                results.append({"file": name, "http_status": response.status, **result})
    report = {
        "kind": "original-sample-replay",
        "not_a_performance_benchmark": True,
        "test_id": args.test_id or "attachment-probe-001",
        "elapsed_seconds": time.monotonic() - start,
        "messages": len(results),
        "statuses": dict(collections.Counter(r["status"] for r in results)),
        "results": results,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "results"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
