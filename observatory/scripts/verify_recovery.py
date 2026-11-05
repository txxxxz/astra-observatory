#!/usr/bin/env python3
"""Verify ACKed records survive SIGKILL and retry remains idempotent.

Kills/restarts only this Compose project's app. Does not delete volumes or data.
"""

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import time
import urllib.parse
import urllib.request


def call(url, payload=None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.load(res)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument(
        "--output", type=pathlib.Path, default=pathlib.Path("evidence/recovery.json")
    )
    args = p.parse_args()
    root = pathlib.Path(__file__).resolve().parents[1]
    run = "recovery-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = args.base_url.rstrip("/")
    types = {
        "kind": "types",
        "test_id": run,
        "revision": 1,
        "changes": [
            {"op": "create", "node": {"type_id": 1, "parent_id": 0, "name": "恢复验证"}}
        ],
    }
    messages = [
        {
            "kind": "objects",
            "test_id": run,
            "batch_id": i,
            "tree_revision": 1,
            "objects": [
                {
                    "id": f"{run}-{i}",
                    "sequence": i,
                    "type_id": 1,
                    "name": f"确认对象 {i}",
                    "timestamp_ms": int(time.time() * 1000),
                    "position": None,
                    "attributes": {"nested": {"preserve": ["中文", None, 42]}},
                }
            ],
        }
        for i in range(20)
    ]
    acknowledgements = [call(base + "/ingest", types)]
    acknowledgements += [call(base + "/ingest", m) for m in messages]
    assert all(a["status"] == "applied" for a in acknowledgements), acknowledgements
    before = call(base + "/api/runs/" + run + "/metrics")
    subprocess.run(
        ["docker", "compose", "kill", "-s", "SIGKILL", "app"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["docker", "compose", "up", "-d", "app"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            health = call(base + "/api/health")
            break
        except (OSError, ValueError):
            time.sleep(0.25)
    else:
        raise RuntimeError("App did not recover after SIGKILL")
    after = call(base + "/api/runs/" + run + "/metrics")
    assert after["object_count"] == before["object_count"] == 20
    assert after["message_count"] == before["message_count"]
    message_checks = []
    for ack, original in zip(acknowledgements, [types, *messages]):
        saved_message = call(
            base + "/api/runs/" + run + "/messages/" + str(ack["message_id"])
        )
        expected_hash = hashlib.sha256(
            json.dumps(
                original,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
                allow_nan=False,
            ).encode()
        ).hexdigest()
        assert saved_message["status"] == "applied", saved_message
        assert saved_message["content_hash"] == expected_hash, saved_message
        assert saved_message["raw"] == original, saved_message
        message_checks.append(
            {
                "id": ack["message_id"],
                "status": saved_message["status"],
                "content_hash": expected_hash,
            }
        )
    details = []
    for m in messages:
        obj = m["objects"][0]
        saved = call(
            base
            + "/api/runs/"
            + run
            + "/objects/"
            + urllib.parse.quote(obj["id"], safe="")
        )
        saved = saved["object"]
        assert all(saved.get(k) == v for k, v in obj.items()), (saved, obj)
        details.append(obj["id"])
    retry = call(base + "/ingest", messages[-1])
    assert retry["status"] == "duplicate", retry
    final = call(base + "/api/runs/" + run + "/metrics")
    assert final["object_count"] == 20
    report = {
        "test_id": run,
        "status": "passed",
        "kill_signal": "SIGKILL",
        "acknowledged_messages": len(acknowledgements),
        "objects_checked_field_by_field": len(details),
        "acknowledged_message_checks": message_checks,
        "before": before,
        "after": after,
        "retry": retry,
        "health": health,
        "scope": "Application process/container crash recovery; not a simulated host power loss or filesystem failure.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {
                "status": "passed",
                "test_id": run,
                "objects_checked": len(details),
                "report": str(args.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
