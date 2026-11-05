import copy
import json
import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "test.db")) as c:
        yield c


def tree(run="test", revision=1, changes=None):
    return {
        "kind": "types",
        "test_id": run,
        "revision": revision,
        "changes": changes
        if changes is not None
        else [
            {"op": "create", "node": {"type_id": 1, "parent_id": 0, "name": "万物"}},
            {"op": "create", "node": {"type_id": 2, "parent_id": 1, "name": "星体"}},
            {"op": "create", "node": {"type_id": 3, "parent_id": 1, "name": "生物"}},
        ],
    }


def obj(i="a", **extra):
    return {
        "id": i,
        "sequence": 0,
        "type_id": 2,
        "name": "恒星 " + i,
        "timestamp_ms": 123,
        "position": {
            "frame_id": "galaxy-1",
            "frame_kind": "galactic",
            "unit": "ly",
            "x": 1,
            "y": 2,
            "z": 3,
        },
        "attributes": {"nested": {"中文": [None, "星🌏", 3]}, "mixed": "1"},
        **extra,
    }


def batch(objects=None, run="test", batch_id=0):
    return {
        "kind": "objects",
        "test_id": run,
        "batch_id": batch_id,
        "tree_revision": 1,
        "objects": objects if objects is not None else [obj()],
    }


def post(c, data):
    r = c.post("/ingest", json=data)
    assert r.status_code == 200, r.text
    return r.json()


def test_atomic_duplicate_conflict_and_restart(client):
    post(client, tree())
    original = batch()
    assert post(client, original)["status"] == "applied"
    reordered = json.dumps(original, ensure_ascii=False, indent=2)
    assert client.post("/ingest", content=reordered).json()["status"] == "duplicate"
    changed = copy.deepcopy(original)
    changed["objects"][0]["name"] = "changed"
    assert post(client, changed)["status"] == "conflict"
    m = client.get("/api/runs/test/metrics").json()
    assert (m["object_count"], m["duplicate_count"], m["conflict_count"]) == (1, 1, 1)
    assert (
        client.get("/api/runs/test/objects/a").json()["object"]["attributes"]
        == obj()["attributes"]
    )
    path = client.app.state.store.path
    with TestClient(create_app(db_path=path)) as c2:
        assert c2.get("/api/runs/test/metrics").json()["object_count"] == 1
        assert post(c2, original)["status"] == "duplicate"


def test_invalid_batch_has_no_partial_write(client):
    post(client, tree())
    bad = obj("b")
    bad.pop("type_id")
    r = post(client, batch([obj("a"), bad]))
    assert r["status"] == "quarantined"
    assert client.get("/api/runs/test/objects").json()["items"] == []
    saved = client.get("/api/runs/test/messages/" + str(r["message_id"])).json()
    assert saved["raw"]["objects"][1]["id"] == "b"


def test_changed_existing_object_is_not_silently_overwritten(client):
    post(client, tree())
    post(client, batch())
    r = post(client, batch([obj("b"), obj("a", sequence=99, name="new")], batch_id=1))
    assert r["status"] == "quarantined"
    assert client.get("/api/runs/test/objects/b").status_code == 404
    assert client.get("/api/runs/test/objects/a").json()["object"]["name"] == "恒星 a"


def test_type_moves_gaps_and_cycles(client):
    post(client, tree())
    post(client, batch())
    gap = tree(
        revision=3,
        changes=[
            {"op": "rename", "node": {"type_id": 2, "parent_id": 1, "name": "gap"}}
        ],
    )
    assert post(client, gap)["status"] == "quarantined"
    move = tree(
        revision=2,
        changes=[
            {"op": "move", "node": {"type_id": 2, "parent_id": 3, "name": "星体"}}
        ],
    )
    assert post(client, move)["status"] == "applied"
    assert len(client.get("/api/runs/test/objects?type_id=3").json()["items"]) == 1
    assert (
        len(
            client.get("/api/runs/test/objects?type_id=3&descendants=false").json()[
                "items"
            ]
        )
        == 0
    )
    cyclic = tree(
        revision=3,
        changes=[
            {"op": "move", "node": {"type_id": 3, "parent_id": 2, "name": "生物"}}
        ],
    )
    assert (
        post(client, cyclic)["status"] == "conflict"
    )  # same revision key, different content
    cyclic["revision"] = 4
    assert post(client, cyclic)["status"] == "quarantined"
    assert client.get("/api/runs/test/types").json()["revision"] == 2


def test_current_tree_atomic_cycle_validation(client):
    post(client, tree())
    cyclic = tree(
        revision=2,
        changes=[
            {"op": "move", "node": {"type_id": 1, "parent_id": 2, "name": "万物"}}
        ],
    )
    assert post(client, cyclic)["status"] == "quarantined"
    assert client.get("/api/runs/test/types").json()["revision"] == 1


def test_isolation_cursor_export_and_frame(client):
    for run in ["test", "other"]:
        post(client, tree(run))
        post(client, batch([obj(str(i)) for i in range(6)], run=run))
    p1 = client.get("/api/runs/test/objects?limit=2").json()
    assert len(p1["items"]) == 2 and p1["next_cursor"]
    post(client, batch([obj("later")], batch_id=1))
    p2 = client.get(
        "/api/runs/test/objects",
        params={
            "limit": 10,
            "cursor": p1["next_cursor"],
            "snapshot_max": p1["snapshot_max"],
        },
    ).json()
    assert len(p2["items"]) == 4
    data = client.get(
        "/api/runs/test/export.ndjson", params={"snapshot_max": p1["snapshot_max"]}
    )
    assert len(data.text.splitlines()) == 6
    assert json.loads(data.text.splitlines()[0])["attributes"] == obj()["attributes"]
    assert client.get("/api/runs/other/metrics").json()["object_count"] == 6
    assert client.get("/api/runs/test/points").status_code == 422
    points = client.get(
        "/api/runs/test/points?frame_id=galaxy-1&frame_kind=galactic&unit=ly&limit=3"
    ).json()
    assert len(points["items"]) == 3 and points["total"] == 7
    assert client.get("/api/runs/test/frames").json()["items"][0]["count"] == 7


def test_observed_samples(client):
    archive = Path(__file__).parent / "fixtures/samples.tar.gz"
    statuses = {}
    with tarfile.open(archive) as tf:
        for member in sorted(
            (
                m
                for m in tf.getmembers()
                if Path(m.name).name.startswith("message-") and m.name.endswith(".json")
            ),
            key=lambda m: m.name,
        ):
            r = client.post("/ingest", content=tf.extractfile(member).read())
            assert r.status_code == 200, r.text
            status = r.json()["status"]
            statuses[status] = statuses.get(status, 0) + 1
    m = client.get("/api/runs/attachment-probe-001/metrics").json()
    assert m["revision"] == 11
    assert m["object_count"] == 2080
    assert m["quarantined_count"] == 2
    assert statuses["duplicate"] == 4
    assert m["message_count"] == 117


def test_body_and_capacity_limits(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "small.db", max_body_bytes=100)) as c:
        assert c.post("/ingest", content="x" * 101).status_code == 413
    with TestClient(
        create_app(db_path=tmp_path / "full.db", storage_limit_bytes=1)
    ) as c:
        assert c.post("/ingest", json=tree()).status_code == 503
        assert c.get("/api/runs").json()["items"] == []


def test_unknown_run(client):
    assert client.get("/api/runs/missing/objects").status_code == 404
    assert client.get("/api/runs/missing/export.ndjson").status_code == 404


def test_concurrent_delivery_is_idempotent(client):
    from concurrent.futures import ThreadPoolExecutor

    post(client, tree())
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(
            pool.map(lambda _: client.post("/ingest", json=batch()), range(24))
        )
    assert all(r.status_code == 200 for r in responses)
    assert sum(r.json()["status"] == "applied" for r in responses) == 1
    metrics = client.get("/api/runs/test/metrics").json()
    assert metrics["object_count"] == 1 and metrics["duplicate_count"] == 23


def test_failed_storage_never_returns_success(client, monkeypatch):
    import sqlite3

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O failure")

    monkeypatch.setattr(client.app.state.store, "ingest", broken)
    response = client.post("/ingest", json=tree())
    assert response.status_code == 503
    assert client.get("/api/runs").json()["items"] == []


def test_export_freezes_categories_and_new_rows(client):
    post(client, tree())
    post(client, batch([obj("a", type_id=2), obj("b", type_id=3)]))
    store = client.app.state.store
    snapshot = store.export_snapshot("test", {"type_id": 2, "descendants": True})
    move = tree(
        revision=2,
        changes=[
            {"op": "move", "node": {"type_id": 3, "parent_id": 2, "name": "生物"}}
        ],
    )
    post(client, move)
    post(client, batch([obj("later")], batch_id=1))
    rows = [
        json.loads(line)
        for chunk in store.export_chunks(snapshot, chunk_size=1)
        for line in chunk.splitlines()
    ]
    assert [r["id"] for r in rows] == ["a"]


def test_deep_categories_are_bounded(client):
    deep = tree(
        changes=[
            {"op": "create", "node": {"type_id": i, "parent_id": i - 1, "name": str(i)}}
            for i in range(1, 131)
        ]
    )
    assert post(client, deep)["status"] == "quarantined"
    assert client.get("/api/runs/test/types").json()["items"] == []


def test_scalar_bools_and_nonfinite_coordinates_rejected(client):
    post(client, tree())
    assert post(client, batch([obj(type_id=True)]))["status"] == "quarantined"
    bad = obj()
    bad["position"]["x"] = "nan"
    assert post(client, batch([bad], batch_id=1))["status"] == "quarantined"
    assert (
        client.post(
            "/ingest",
            content='{"test_id":"test","kind":"objects","batch_id":2,"objects":NaN}',
        ).status_code
        == 422
    )


def test_commit_failure_rolls_back_whole_message(client, monkeypatch):
    import sqlite3
    from contextlib import contextmanager

    store = client.app.state.store
    original = store.connect

    @contextmanager
    def failure():
        with original() as conn:

            class Proxy:
                def __getattr__(self, key):
                    return getattr(conn, key)

                def commit(self):
                    raise sqlite3.OperationalError("simulated commit I/O failure")

            yield Proxy()

    monkeypatch.setattr(store, "connect", failure)
    assert client.post("/ingest", json=tree()).status_code == 503
    monkeypatch.setattr(store, "connect", original)
    assert client.get("/api/runs").json()["items"] == []
    assert post(client, tree())["status"] == "applied"


def test_cancelled_request_retains_ingest_admission_until_writer_done(
    tmp_path, monkeypatch
):
    import asyncio
    import threading

    import httpx

    monkeypatch.setenv("OBS_INGEST_CONCURRENCY", "1")
    app = create_app(db_path=tmp_path / "cancel.db")
    entered = threading.Event()
    release = threading.Event()
    original = app.state.store.ingest

    def delayed(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(app.state.store, "ingest", delayed)

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            task = asyncio.create_task(c.post("/ingest", json=tree()))
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert (await c.post("/ingest", json=tree())).status_code == 429
            release.set()
            while app.state.pending_ingest:
                await asyncio.sleep(0.01)
            response = await c.post("/ingest", json=tree())
            assert (
                response.status_code == 200 and response.json()["status"] == "duplicate"
            )

    asyncio.run(check())


def test_stream_admission_released_when_client_disconnects():
    import asyncio

    from starlette.requests import ClientDisconnect

    from backend.app import LeaseStreamingResponse

    released = []
    response = LeaseStreamingResponse(
        iter([b"first", b"second"]), release=lambda: released.append(True)
    )

    async def send(_message):
        raise OSError("client gone")

    async def receive():
        return {"type": "http.disconnect"}

    async def check():
        with pytest.raises((ClientDisconnect, OSError)):
            await response(
                {"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send
            )

    asyncio.run(check())
    assert released == [True]
