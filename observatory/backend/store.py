"""SQLite durable inbox and synchronous, atomic projections.

Every successful ingestion call has committed its original message and projection
(or quarantine reason). No accepted work exists only in process memory.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import sqlite3
import threading
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class CapacityError(Exception):
    pass


class InvalidMessage(ValueError):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def integer(value, label, minimum=0):
    if type(value) is not int or not minimum <= value <= 2**63 - 1:
        raise InvalidMessage(f"{label}: expected integer >= {minimum}")
    return value


def string(value, label, maximum=1024, empty=False):
    if (
        not isinstance(value, str)
        or (not value and not empty)
        or len(value) > maximum
        or "\x00" in value
    ):
        raise InvalidMessage(
            f"{label}: expected nonempty string, at most {maximum} characters"
        )
    return value


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
 test_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 object_count INTEGER NOT NULL DEFAULT 0, message_count INTEGER NOT NULL DEFAULT 0,
 duplicate_count INTEGER NOT NULL DEFAULT 0, quarantined_count INTEGER NOT NULL DEFAULT 0,
 conflict_count INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0,
 received_objects INTEGER NOT NULL DEFAULT 0, applied_objects INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY AUTOINCREMENT, test_id TEXT NOT NULL REFERENCES runs(test_id),
 kind TEXT NOT NULL, message_key TEXT NOT NULL, content_hash TEXT NOT NULL,
 status TEXT NOT NULL, reason TEXT, received_at TEXT NOT NULL, received_epoch REAL NOT NULL,
 object_count INTEGER NOT NULL DEFAULT 0, applied_objects INTEGER NOT NULL DEFAULT 0,
 duplicate_count INTEGER NOT NULL DEFAULT 0, raw BLOB NOT NULL,
 UNIQUE(test_id,kind,message_key,content_hash)
);
CREATE INDEX IF NOT EXISTS messages_identity ON messages(test_id,kind,message_key,id);
CREATE INDEX IF NOT EXISTS messages_recent ON messages(test_id,received_epoch,id);
CREATE INDEX IF NOT EXISTS messages_status ON messages(test_id,status,id);
CREATE TABLE IF NOT EXISTS types (
 test_id TEXT NOT NULL, type_id INTEGER NOT NULL, parent_id INTEGER NOT NULL, name TEXT NOT NULL,
 object_count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(test_id,type_id),
 FOREIGN KEY(test_id) REFERENCES runs(test_id)
);
CREATE INDEX IF NOT EXISTS types_parent ON types(test_id,parent_id);
CREATE TABLE IF NOT EXISTS type_changes (
 test_id TEXT NOT NULL, revision INTEGER NOT NULL, changes TEXT NOT NULL, received_at TEXT NOT NULL,
 PRIMARY KEY(test_id,revision)
);
CREATE TABLE IF NOT EXISTS objects (
 row_id INTEGER PRIMARY KEY AUTOINCREMENT, test_id TEXT NOT NULL, id TEXT NOT NULL,
 type_id INTEGER NOT NULL, name TEXT NOT NULL, sequence INTEGER NOT NULL, timestamp_ms INTEGER NOT NULL,
 frame_id TEXT, frame_kind TEXT, unit TEXT, x REAL, y REAL, z REAL,
 tree_revision INTEGER NOT NULL, received_at TEXT NOT NULL, content_hash TEXT NOT NULL, payload TEXT NOT NULL,
 UNIQUE(test_id,id), FOREIGN KEY(test_id,type_id) REFERENCES types(test_id,type_id)
);
CREATE INDEX IF NOT EXISTS objects_run_row ON objects(test_id,row_id);
CREATE INDEX IF NOT EXISTS objects_type_row ON objects(test_id,type_id,row_id);
CREATE INDEX IF NOT EXISTS objects_name ON objects(test_id,name COLLATE NOCASE,row_id);
CREATE INDEX IF NOT EXISTS objects_frame_row ON objects(test_id,frame_id,frame_kind,unit,row_id);
CREATE TABLE IF NOT EXISTS frames (
 test_id TEXT NOT NULL, frame_id TEXT NOT NULL, frame_kind TEXT NOT NULL, unit TEXT NOT NULL,
 count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(test_id,frame_id,frame_kind,unit)
);
"""


class Store:
    def __init__(self, path, storage_limit_bytes=19 * 1024**3, write_timeout=5):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_limit_bytes = storage_limit_bytes
        self.write_timeout = write_timeout
        self.writer = threading.Lock()
        self.started = time.monotonic()
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(
            self.path, timeout=self.write_timeout, isolation_level=None
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA cache_size=-8192")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
        finally:
            conn.close()

    def storage_bytes(self):
        # The dedicated data directory contains DB, WAL, shared memory and logs.
        total = 0
        for file in self.path.parent.iterdir():
            try:
                if file.is_file():
                    total += file.stat().st_size
            except FileNotFoundError:
                pass  # WAL may be checkpointed between list/stat.
        return total

    def ensure_capacity(self, size):
        reserve = max(1024 * 1024, size * 6)
        if self.storage_bytes() + reserve >= self.storage_limit_bytes:
            raise CapacityError("storage soft limit reached; no message acknowledged")
        if shutil.disk_usage(self.path.parent).free < reserve + 8 * 1024 * 1024:
            raise CapacityError("insufficient free disk space; no message acknowledged")

    def ingest(self, data, raw):
        run = string(data.get("test_id"), "test_id", 256)
        if run in (".", "..") or "/" in run or "\\" in run:
            raise InvalidMessage(
                "test_id must be one URL path segment (no slash or dot segment)"
            )
        kind = data.get("kind") if isinstance(data.get("kind"), str) else "unknown"
        kind = kind[:128]
        key_field = "revision" if kind == "types" else "batch_id"
        value = data.get(key_field)
        content_hash = digest(data)
        key = (
            str(value)
            if type(value) is int or isinstance(value, str)
            else "missing:" + content_hash
        )
        key = key[:512]
        count = len(data["objects"]) if isinstance(data.get("objects"), list) else 0
        if not self.writer.acquire(timeout=self.write_timeout):
            raise CapacityError("writer busy; retry later")
        try:
            self.ensure_capacity(len(raw))
            with self.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    now = stamp()
                    conn.execute(
                        "INSERT OR IGNORE INTO runs(test_id,created_at,updated_at) VALUES(?,?,?)",
                        (run, now, now),
                    )
                    existing = conn.execute(
                        "SELECT id,status FROM messages WHERE test_id=? AND kind=? AND message_key=? AND content_hash=?",
                        (run, kind, key, content_hash),
                    ).fetchone()
                    if existing:
                        conn.execute(
                            "UPDATE runs SET duplicate_count=duplicate_count+1,updated_at=? WHERE test_id=?",
                            (now, run),
                        )
                        conn.execute(
                            "UPDATE messages SET duplicate_count=duplicate_count+1 WHERE id=?",
                            (existing["id"],),
                        )
                        conn.commit()
                        return {
                            "status": "duplicate",
                            "message_id": existing["id"],
                            "original_status": existing["status"],
                        }
                    conflict = conn.execute(
                        "SELECT id FROM messages WHERE test_id=? AND kind=? AND message_key=? LIMIT 1",
                        (run, kind, key),
                    ).fetchone()
                    status, reason, applied = "applied", None, 0
                    if conflict:
                        status, reason = (
                            "conflict",
                            f"message_key_conflict: existing message {conflict[0]} has different content",
                        )
                    else:
                        conn.execute("SAVEPOINT projection")
                        try:
                            if kind == "types":
                                self.apply_types(conn, run, data, now)
                            elif kind == "objects":
                                applied = self.apply_objects(conn, run, data, now)
                            else:
                                raise InvalidMessage(f"unknown kind: {kind}")
                            conn.execute("RELEASE projection")
                        except (
                            InvalidMessage,
                            KeyError,
                            TypeError,
                            ValueError,
                            OverflowError,
                        ) as exc:
                            conn.execute("ROLLBACK TO projection")
                            conn.execute("RELEASE projection")
                            status, reason, applied = "quarantined", str(exc)[:1500], 0
                    cursor = conn.execute(
                        "INSERT INTO messages(test_id,kind,message_key,content_hash,status,reason,received_at,received_epoch,object_count,applied_objects,raw) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            run,
                            kind,
                            key,
                            content_hash,
                            status,
                            reason,
                            now,
                            time.time(),
                            count,
                            applied,
                            raw,
                        ),
                    )
                    conn.execute(
                        "UPDATE runs SET updated_at=?,message_count=message_count+1,received_objects=received_objects+?,object_count=object_count+?,applied_objects=applied_objects+?,quarantined_count=quarantined_count+?,conflict_count=conflict_count+? WHERE test_id=?",
                        (
                            now,
                            count,
                            applied,
                            applied,
                            int(status == "quarantined"),
                            int(status == "conflict"),
                            run,
                        ),
                    )
                    conn.commit()
                    result = {"status": status, "message_id": cursor.lastrowid}
                    if reason:
                        result["reason"] = reason
                    return result
                except BaseException:
                    conn.rollback()
                    raise
        finally:
            self.writer.release()

    def apply_types(self, conn, run, data, now):
        revision = integer(data.get("revision"), "revision", 1)
        current = conn.execute(
            "SELECT revision FROM runs WHERE test_id=?", (run,)
        ).fetchone()[0]
        if revision != current + 1:
            raise InvalidMessage(
                f"revision_gap: expected {current + 1}, received {revision}; isolated, no automatic replay"
            )
        changes = data.get("changes")
        if not isinstance(changes, list) or not changes or len(changes) > 10000:
            raise InvalidMessage(
                "changes must be a nonempty array with <=10000 entries"
            )
        nodes = {
            r["type_id"]: dict(r)
            for r in conn.execute("SELECT * FROM types WHERE test_id=?", (run,))
        }
        for change in changes:
            if not isinstance(change, dict) or not isinstance(change.get("node"), dict):
                raise InvalidMessage("type change/node must be an object")
            node = change["node"]
            tid = integer(node.get("type_id"), "type_id", 1)
            parent = integer(node.get("parent_id"), "parent_id")
            name = string(node.get("name"), "type name", 1024)
            op = change.get("op")
            if op == "create":
                if tid in nodes:
                    raise InvalidMessage(f"create existing type_id {tid}")
                nodes[tid] = {
                    "type_id": tid,
                    "parent_id": parent,
                    "name": name,
                    "object_count": 0,
                }
            elif op in ("rename", "move"):
                if tid not in nodes:
                    raise InvalidMessage(f"{op} missing type_id {tid}")
                if op == "rename" and parent != nodes[tid]["parent_id"]:
                    raise InvalidMessage("rename unexpectedly changes parent; use move")
                nodes[tid].update(parent_id=parent, name=name)
            else:
                raise InvalidMessage(f"unknown type operation: {op}")
        if len(nodes) > 100000:
            raise InvalidMessage("category limit 100000 reached")
        for tid, node in nodes.items():
            seen = {tid}
            parent = node["parent_id"]
            while parent:
                if parent not in nodes:
                    raise InvalidMessage(f"unknown parent_id {parent}")
                if parent in seen:
                    raise InvalidMessage("classification cycle")
                seen.add(parent)
                if len(seen) > 128:
                    raise InvalidMessage("classification depth exceeds 128")
                parent = nodes[parent]["parent_id"]
        conn.executemany(
            "INSERT INTO types(test_id,type_id,parent_id,name,object_count) VALUES(?,?,?,?,?) ON CONFLICT(test_id,type_id) DO UPDATE SET parent_id=excluded.parent_id,name=excluded.name",
            [
                (run, n["type_id"], n["parent_id"], n["name"], n["object_count"])
                for n in nodes.values()
            ],
        )
        conn.execute(
            "INSERT INTO type_changes VALUES(?,?,?,?)",
            (run, revision, compact(changes), now),
        )
        conn.execute("UPDATE runs SET revision=? WHERE test_id=?", (revision, run))

    def apply_objects(self, conn, run, data, now):
        integer(data.get("batch_id"), "batch_id")
        revision = integer(data.get("tree_revision"), "tree_revision", 1)
        current = conn.execute(
            "SELECT revision FROM runs WHERE test_id=?", (run,)
        ).fetchone()[0]
        if revision > current:
            raise InvalidMessage(f"tree_revision_not_applied: {revision} > {current}")
        values = data.get("objects")
        if not isinstance(values, list) or len(values) > 20000:
            raise InvalidMessage("objects must be an array with <=20000 entries")
        types = {
            r[0]
            for r in conn.execute("SELECT type_id FROM types WHERE test_id=?", (run,))
        }
        prepared, seen = [], {}
        for obj in values:
            if not isinstance(obj, dict):
                raise InvalidMessage("object entry must be an object")
            oid = string(obj.get("id"), "object id", 512)
            tid = integer(obj.get("type_id"), "object type_id", 1)
            if tid not in types:
                raise InvalidMessage(f"unknown type_id {tid}")
            name = string(obj.get("name"), "object name", 4096, empty=True)
            sequence = integer(obj.get("sequence"), "sequence")
            timestamp = integer(obj.get("timestamp_ms"), "timestamp_ms")
            if not isinstance(obj.get("attributes"), dict):
                raise InvalidMessage(f"object {oid}: attributes must be an object")
            position = obj.get("position")
            frame = (None, None, None, None, None, None)
            if position is not None:
                if not isinstance(position, dict):
                    raise InvalidMessage("position must be an object or null")
                frame = tuple(
                    string(position.get(k), k, 512)
                    for k in ("frame_id", "frame_kind", "unit")
                )
                coords = []
                for k in ("x", "y", "z"):
                    value = position.get(k)
                    if (
                        type(value) not in (int, float)
                        or not math.isfinite(value)
                        or abs(value) > 1e100
                    ):
                        raise InvalidMessage(
                            f"position.{k}: expected finite numeric coordinate <=1e100"
                        )
                    coords.append(value)
                frame += tuple(coords)
            obj_hash = digest(obj)
            if oid in seen:
                if seen[oid] != obj_hash:
                    raise InvalidMessage(
                        f"object_conflict: {oid}; repeated ID with different contents in batch"
                    )
                continue
            seen[oid] = obj_hash
            prepared.append(
                (
                    run,
                    oid,
                    tid,
                    name,
                    sequence,
                    timestamp,
                    *frame,
                    revision,
                    now,
                    obj_hash,
                    compact(obj),
                )
            )
        existing = {}
        ids = list(seen)
        for start in range(0, len(ids), 400):
            chunk = ids[start : start + 400]
            existing.update(
                (r[0], r[1])
                for r in conn.execute(
                    "SELECT id,content_hash FROM objects WHERE test_id=? AND id IN ("
                    + ",".join("?" for _ in chunk)
                    + ")",
                    [run, *chunk],
                )
            )
        for oid, obj_hash in existing.items():
            if seen[oid] != obj_hash:
                raise InvalidMessage(
                    f"object_conflict: {oid}; update semantics unknown, whole message isolated"
                )
        fresh = [row for row in prepared if row[1] not in existing]
        conn.executemany(
            "INSERT INTO objects(test_id,id,type_id,name,sequence,timestamp_ms,frame_id,frame_kind,unit,x,y,z,tree_revision,received_at,content_hash,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            fresh,
        )
        category_counts = Counter(row[2] for row in fresh)
        conn.executemany(
            "UPDATE types SET object_count=object_count+? WHERE test_id=? AND type_id=?",
            [(count, run, tid) for tid, count in category_counts.items()],
        )
        frame_counts = Counter(row[6:9] for row in fresh if row[6] is not None)
        conn.executemany(
            "INSERT INTO frames(test_id,frame_id,frame_kind,unit,count) VALUES(?,?,?,?,?) ON CONFLICT(test_id,frame_id,frame_kind,unit) DO UPDATE SET count=count+excluded.count",
            [(run, *frame, count) for frame, count in frame_counts.items()],
        )
        return len(fresh)

    def run(self, conn, run):
        if not conn.in_transaction:
            conn.execute("BEGIN")
        row = conn.execute("SELECT * FROM runs WHERE test_id=?", (run,)).fetchone()
        if row is None:
            raise KeyError(run)
        return dict(row)

    def runs(self):
        with self.connect() as conn:
            return {
                "items": [
                    dict(r)
                    for r in conn.execute(
                        "SELECT * FROM runs ORDER BY created_at DESC LIMIT 200"
                    )
                ]
            }

    def type_rows(self, conn, run):
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT type_id,parent_id,name,object_count FROM types WHERE test_id=? ORDER BY type_id",
                (run,),
            )
        ]
        by_id = {r["type_id"]: r for r in rows}
        for r in rows:
            r["subtree_count"] = r["object_count"]
        for r in rows:
            parent = r["parent_id"]
            while parent in by_id:
                by_id[parent]["subtree_count"] += r["object_count"]
                parent = by_id[parent]["parent_id"]
        return rows

    def types(self, run):
        with self.connect() as conn:
            record = self.run(conn, run)
            rows = self.type_rows(conn, run)
            changes = [
                {
                    "revision": r["revision"],
                    "changes": json.loads(r["changes"]),
                    "received_at": r["received_at"],
                }
                for r in conn.execute(
                    "SELECT * FROM type_changes WHERE test_id=? ORDER BY revision DESC LIMIT 30",
                    (run,),
                )
            ]
            return {"revision": record["revision"], "items": rows, "changes": changes}

    def frame_rows(self, conn, run):
        return [
            dict(r)
            for r in conn.execute(
                "SELECT frame_id,frame_kind,unit,count FROM frames WHERE test_id=? ORDER BY count DESC,frame_id LIMIT 10000",
                (run,),
            )
        ]

    def frames(self, run):
        with self.connect() as conn:
            self.run(conn, run)
            return {"items": self.frame_rows(conn, run)}

    def metrics(self, run):
        with self.connect() as conn:
            record = self.run(conn, run)
            rates = conn.execute(
                "SELECT coalesce(sum(applied_objects),0),count(*) FROM messages WHERE test_id=? AND received_epoch>=?",
                (run, time.time() - 10),
            ).fetchone()
            record.update(
                rate_objects_per_second=rates[0] / 10,
                rate_messages_per_second=rates[1] / 10,
                database_bytes=self.storage_bytes(),
                storage_limit_bytes=self.storage_limit_bytes,
                backlog=0,
                frames=self.frame_rows(conn, run),
                categories=self.type_rows(conn, run),
                recent_messages=self.message_rows(conn, run, 20, None),
                uptime_seconds=round(time.monotonic() - self.started, 2),
            )
            return record

    def filter(self, conn, run, filters, freeze_types=None):
        parts = ["o.test_id=?"]
        args = [run]
        tid = filters.get("type_id")
        if tid is not None:
            ids = freeze_types
            if ids is None:
                ids = [tid]
                if filters.get("descendants", True):
                    ids = [
                        r[0]
                        for r in conn.execute(
                            "WITH RECURSIVE subtree(type_id) AS (SELECT type_id FROM types WHERE test_id=? AND type_id=? UNION ALL SELECT t.type_id FROM types t JOIN subtree s ON t.parent_id=s.type_id WHERE t.test_id=?) SELECT type_id FROM subtree",
                            (run, tid, run),
                        )
                    ]
            if not ids:
                parts.append("0")
            else:
                # One bound JSON array works for the full category limit even
                # when SQLite is compiled with its default 32766 bind limit.
                parts.append("o.type_id IN (SELECT value FROM json_each(?))")
                args.append(compact(ids))
        for field in ("object_id", "frame_id", "frame_kind", "unit"):
            if filters.get(field) is not None:
                parts.append("o." + ("id" if field == "object_id" else field) + "=?")
                args.append(filters[field])
        prefix = filters.get("name_prefix")
        if prefix:
            parts.append("o.name LIKE ? ESCAPE '\\'")
            args.append(
                prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                + "%"
            )
        return " AND ".join(parts), args

    @staticmethod
    def brief(row):
        result = {
            k: row[k]
            for k in (
                "row_id",
                "id",
                "name",
                "type_id",
                "type_name",
                "sequence",
                "timestamp_ms",
            )
        }
        result["position"] = (
            {k: row[k] for k in ("frame_id", "frame_kind", "unit", "x", "y", "z")}
            if row["frame_id"] is not None
            else None
        )
        return result

    def objects(self, run, filters, limit=50, cursor=0, snapshot_max=None):
        with self.connect() as conn:
            self.run(conn, run)
            if snapshot_max is None:
                snapshot_max = conn.execute(
                    "SELECT coalesce(max(row_id),0) FROM objects WHERE test_id=?",
                    (run,),
                ).fetchone()[0]
            where, args = self.filter(conn, run, filters)
            rows = conn.execute(
                "SELECT o.row_id,o.id,o.name,o.type_id,o.sequence,o.timestamp_ms,o.frame_id,o.frame_kind,o.unit,o.x,o.y,o.z,t.name AS type_name FROM objects o JOIN types t ON t.test_id=o.test_id AND t.type_id=o.type_id WHERE "
                + where
                + " AND o.row_id>? AND o.row_id<=? ORDER BY o.row_id LIMIT ?",
                [*args, cursor, snapshot_max, limit + 1],
            ).fetchall()
            items = [self.brief(r) for r in rows[:limit]]
            return {
                "items": items,
                "next_cursor": str(items[-1]["row_id"]) if len(rows) > limit else None,
                "snapshot_max": snapshot_max,
            }

    def object(self, run, oid):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT o.payload,o.row_id,o.tree_revision,o.received_at,t.name AS type_name FROM objects o JOIN types t ON t.test_id=o.test_id AND t.type_id=o.type_id WHERE o.test_id=? AND o.id=?",
                (run, oid),
            ).fetchone()
            if row is None:
                raise KeyError(oid)
            return {
                "object": json.loads(row["payload"]),
                "meta": {
                    k: row[k]
                    for k in ("row_id", "tree_revision", "received_at", "type_name")
                },
            }

    def points(self, run, filters, limit):
        with self.connect() as conn:
            self.run(conn, run)
            where, args = self.filter(conn, run, filters)
            rows = conn.execute(
                "SELECT o.id,o.name,o.type_id,o.x,o.y,o.z FROM objects o WHERE "
                + where
                + " ORDER BY o.row_id LIMIT ?",
                [*args, limit],
            ).fetchall()
            # Frame totals are incremental; combined filters have indexed bounded scans.
            if (
                not filters.get("type_id")
                and not filters.get("object_id")
                and not filters.get("name_prefix")
            ):
                count = conn.execute(
                    "SELECT count FROM frames WHERE test_id=? AND frame_id=? AND frame_kind=? AND unit=?",
                    (run, filters["frame_id"], filters["frame_kind"], filters["unit"]),
                ).fetchone()
                total = count[0] if count else 0
            else:
                total = conn.execute(
                    "SELECT count(*) FROM objects o WHERE " + where, args
                ).fetchone()[0]
            return {
                "items": [dict(r) for r in rows],
                "frame": {k: filters[k] for k in ("frame_id", "frame_kind", "unit")},
                "limit": limit,
                "sampled": True,
                "total": total,
                "sampling": "earliest matching objects by durable row_id",
            }

    def export_snapshot(self, run, filters, snapshot_max=None):
        with self.connect() as conn:
            conn.execute("BEGIN")
            self.run(conn, run)
            maximum = conn.execute(
                "SELECT coalesce(max(row_id),0) FROM objects WHERE test_id=?", (run,)
            ).fetchone()[0]
            maximum = (
                min(maximum, snapshot_max) if snapshot_max is not None else maximum
            )
            # Build SQL and parameters once: the descendant set cannot change mid-stream.
            where, args = self.filter(conn, run, filters)
            return where, args, maximum

    def export_chunks(self, snapshot, chunk_size=200, chunk_bytes=1024 * 1024):
        where, args, maximum = snapshot
        cursor = 0
        while cursor < maximum:
            with self.connect() as conn:
                # Read only IDs and UTF-8 byte lengths first. A row-count cap
                # alone could materialize 200 nearly-8-MiB objects at once.
                candidates = conn.execute(
                    "SELECT o.row_id,length(CAST(o.payload AS BLOB))+1 AS bytes FROM objects o WHERE "
                    + where
                    + " AND o.row_id>? AND o.row_id<=? ORDER BY o.row_id LIMIT ?",
                    [*args, cursor, maximum, chunk_size],
                ).fetchall()
                if not candidates:
                    break
                upper, size = cursor, 0
                for candidate in candidates:
                    # An oversized individual object is emitted on its own;
                    # its size is bounded by the ingestion request-body limit.
                    if upper != cursor and size + candidate["bytes"] > chunk_bytes:
                        break
                    upper = candidate["row_id"]
                    size += candidate["bytes"]
                rows = conn.execute(
                    "SELECT o.payload FROM objects o WHERE "
                    + where
                    + " AND o.row_id>? AND o.row_id<=? ORDER BY o.row_id",
                    [*args, cursor, upper],
                ).fetchall()
            cursor = upper
            yield b"".join(row["payload"].encode() + b"\n" for row in rows)

    def message_rows(self, conn, run, limit, status):
        condition = "test_id=?"
        args = [run]
        if status:
            condition += " AND status=?"
            args.append(status)
        return [
            dict(r)
            for r in conn.execute(
                "SELECT id,kind,message_key,status,reason,received_at,object_count,applied_objects,duplicate_count FROM messages WHERE "
                + condition
                + " ORDER BY id DESC LIMIT ?",
                [*args, limit],
            )
        ]

    def messages(self, run, limit, status):
        with self.connect() as conn:
            self.run(conn, run)
            return {"items": self.message_rows(conn, run, limit, status)}

    def message(self, run, mid):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM messages WHERE test_id=? AND id=?", (run, mid)
            ).fetchone()
            if row is None:
                raise KeyError(mid)
            result = dict(row)
            result["raw"] = json.loads(result["raw"])
            return result
