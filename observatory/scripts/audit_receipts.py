#!/usr/bin/env python3
"""Reconcile real generator ACK bitmaps with the persisted SQLite message ledger."""

import argparse
import base64
import collections
import gzip
import json
import pathlib
import subprocess


def bits(encoded):
    return {
        8 * i + bit
        for i, byte in enumerate(base64.b64decode(encoded))
        for bit in range(8)
        if byte & (1 << bit)
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="astra-observatory-app-1")
    parser.add_argument(
        "--reports", type=pathlib.Path, default=pathlib.Path("evidence/benchmarks")
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path("evidence/receipt-audit.json"),
    )
    args = parser.parse_args()
    results = []
    source = "import sqlite3,os,json,sys; c=sqlite3.connect('file:'+os.environ['OBS_DB_PATH']+'?mode=ro',uri=True); c.row_factory=sqlite3.Row; print(json.dumps([dict(r) for r in c.execute(\"SELECT id,message_key,status,object_count,applied_objects FROM messages WHERE test_id=? AND kind='objects'\",(sys.argv[1],))]))"
    for file in sorted(args.reports.glob("*.json*")):
        if file.suffix == ".gz" and file.with_suffix("").exists():
            continue
        raw = (
            gzip.decompress(file.read_bytes())
            if file.suffix == ".gz"
            else file.read_bytes()
        )
        report = json.loads(raw)
        receipt = report["receipt"]
        ack = bits(receipt["ack_bitmap"])
        sent = bits(receipt["sent_bitmap"])
        rows = json.loads(
            subprocess.check_output(
                [
                    "docker",
                    "exec",
                    args.container,
                    "python",
                    "-c",
                    source,
                    report["test_id"],
                ],
                text=True,
            )
        )
        by_key = {int(r["message_key"]): r for r in rows if r["message_key"].isdigit()}
        missing = sorted(ack - by_key.keys())
        bad = [
            {"batch_id": i, **by_key[i]}
            for i in sorted(ack & by_key.keys())
            if by_key[i]["status"] != "applied"
        ]
        committed_unack = [
            {"batch_id": i, **by_key[i]}
            for i in sorted((sent - ack) & by_key.keys())
            if by_key[i]["status"] == "applied"
        ]
        confirmed_objects = sum(
            by_key[i]["applied_objects"] for i in ack if i in by_key
        )
        stats = receipt["stats"]
        counts_match = (
            len(ack) == stats["acknowledged_batches"]
            and confirmed_objects == stats["acknowledged_objects"]
        )
        item = {
            "test_id": report["test_id"],
            "sent_bitmap_batches": len(sent),
            "ack_bitmap_batches": len(ack),
            "all_acknowledged_batches_persisted_and_applied": not missing and not bad,
            "missing_acknowledged_batches": missing,
            "acknowledged_nonapplied_batches": bad,
            "acknowledged_objects_found": confirmed_objects,
            "bitmap_database_and_receipt_counts_match": counts_match,
            "committed_unacknowledged_batches": committed_unack,
            "injection_message_statuses": dict(
                collections.Counter(
                    r["status"] for r in rows if int(r["message_key"]) not in sent
                )
            ),
            "interrupted_requests": stats["interrupted_requests"],
        }
        results.append(item)
    passed = bool(results) and all(
        r["all_acknowledged_batches_persisted_and_applied"]
        and r["bitmap_database_and_receipt_counts_match"]
        for r in results
    )
    output = {
        "status": "passed" if passed else "failed",
        "runs": results,
        "scope": "Receipt main-stream bitmaps reconciled with persisted message ledger; fault injections counted separately. Committed requests without observed ACK may safely be retried.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
