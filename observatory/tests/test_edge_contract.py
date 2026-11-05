"""Independent edge cases for the public ingest/query contract."""


import pytest
from fastapi.testclient import TestClient

from backend.app import create_app


@pytest.fixture
def api(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "edges.db")) as c:
        r = c.post(
            "/ingest",
            json={
                "test_id": "edge",
                "kind": "types",
                "revision": 1,
                "changes": [
                    {
                        "op": "create",
                        "node": {"type_id": 1, "parent_id": 0, "name": "root"},
                    },
                    {
                        "op": "create",
                        "node": {"type_id": 2, "parent_id": 1, "name": "leaf"},
                    },
                ],
            },
        )
        assert r.status_code == 200
        yield c


def item(oid="a", name="星🌌"):
    return {
        "id": oid,
        "type_id": 2,
        "sequence": 0,
        "name": name,
        "timestamp_ms": 123,
        "position": None,
        "attributes": {
            "scalar": None,
            "array": [1, "1", None],
            "nested": {"中文": "换行\n数据"},
        },
    }


def put(c, objects, batch=0):
    return c.post(
        "/ingest",
        json={
            "test_id": "edge",
            "kind": "objects",
            "batch_id": batch,
            "tree_revision": 1,
            "objects": objects,
        },
    )


def test_exact_same_object_in_distinct_messages_counts_entity_once(api):
    assert put(api, [item()]).json()["status"] == "applied"
    assert put(api, [item()], batch=1).json()["status"] == "applied"
    m = api.get("/api/runs/edge/metrics").json()
    assert m["object_count"] == 1
    assert len(api.get("/api/runs/edge/export.ndjson").text.splitlines()) == 1


def test_conflicting_ids_inside_one_message_leave_no_partial_state(api):
    other = item()
    other["attributes"]["scalar"] = "different"
    response = put(api, [item("before"), item(), other])
    assert response.status_code == 200
    assert response.json()["status"] == "quarantined"
    assert api.get("/api/runs/edge/objects").json()["items"] == []


def test_unicode_and_unknown_nested_properties_survive_roundtrip(api):
    raw = item()
    raw["new_extension"] = {"unknown": ["retained", {"value": 42}]}
    assert put(api, [raw]).json()["status"] == "applied"
    detail = api.get("/api/runs/edge/objects/a").json()["object"]
    for key, value in raw.items():
        assert detail[key] == value


def test_name_prefix_treats_sql_wildcards_literally(api):
    assert (
        put(
            api, [item("a", "a%real"), item("b", "anything"), item("c", "a_real")]
        ).json()["status"]
        == "applied"
    )
    assert [
        x["id"]
        for x in api.get("/api/runs/edge/objects", params={"name_prefix": "a%"}).json()[
            "items"
        ]
    ] == ["a"]
    assert [
        x["id"]
        for x in api.get("/api/runs/edge/objects", params={"name_prefix": "a_"}).json()[
            "items"
        ]
    ] == ["c"]


def test_no_coordinate_objects_are_searchable_and_exportable(api):
    assert put(api, [item()]).json()["status"] == "applied"
    assert api.get("/api/runs/edge/frames").json()["items"] == []
    assert api.get("/api/runs/edge/objects/a").json()["object"]["position"] is None
    assert len(api.get("/api/runs/edge/export.ndjson").text.splitlines()) == 1


def test_unknown_type_whole_message_quarantined_and_raw_visible(api):
    unknown = item("unknown")
    unknown["type_id"] = 999
    response = put(api, [item("valid"), unknown]).json()
    assert response["status"] == "quarantined"
    assert api.get("/api/runs/edge/objects").json()["items"] == []
    saved = api.get("/api/runs/edge/messages/" + str(response["message_id"])).json()
    assert saved["raw"]["objects"][1]["type_id"] == 999


def test_frame_filter_respects_all_three_identifiers(api):
    values = []
    for oid, kind, unit in [("a", "galactic", "ly"), ("b", "local_surface", "m")]:
        o = item(oid)
        o["position"] = {
            "frame_id": "same-name",
            "frame_kind": kind,
            "unit": unit,
            "x": 1,
            "y": 2,
            "z": 3,
        }
        values.append(o)
    assert put(api, values).json()["status"] == "applied"
    points = api.get(
        "/api/runs/edge/points",
        params={"frame_id": "same-name", "frame_kind": "galactic", "unit": "ly"},
    ).json()
    assert [o["id"] for o in points["items"]] == ["a"]
    rows = api.get(
        "/api/runs/edge/export.ndjson",
        params={"frame_id": "same-name", "frame_kind": "local_surface", "unit": "m"},
    )
    assert '"id":"b"' in rows.text.replace(" ", "")
    assert len(rows.text.splitlines()) == 1


def test_mutating_invalid_types_transaction_rolls_back_all_changes(api):
    response = api.post(
        "/ingest",
        json={
            "kind": "types",
            "test_id": "edge",
            "revision": 2,
            "changes": [
                {
                    "op": "rename",
                    "node": {"type_id": 2, "parent_id": 1, "name": "temporary"},
                },
                {"op": "move", "node": {"type_id": 1, "parent_id": 2, "name": "root"}},
            ],
        },
    ).json()
    assert response["status"] == "quarantined"
    tree = api.get("/api/runs/edge/types").json()
    assert tree["revision"] == 1
    assert next(o for o in tree["items"] if o["type_id"] == 2)["name"] == "leaf"


def test_export_chunk_memory_bound_is_bytes_not_object_count(api):
    values = [item(str(i)) for i in range(12)]
    for value in values:
        value["attributes"]["large"] = "星" * 60_000
    assert put(api, values).json()["status"] == "applied"
    store = api.app.state.store
    chunks = list(store.export_chunks(store.export_snapshot("edge", {})))
    assert len(chunks) > 1
    assert max(map(len, chunks)) <= 1024 * 1024
    import json

    exported = [json.loads(line) for chunk in chunks for line in chunk.splitlines()]
    assert exported == values


def test_single_large_object_is_exported_without_coalescing_more(api):
    values = [item(str(i)) for i in range(3)]
    values[0]["attributes"]["large"] = "x" * (2 * 1024 * 1024)
    assert put(api, values).json()["status"] == "applied"
    store = api.app.state.store
    chunks = list(store.export_chunks(store.export_snapshot("edge", {})))
    assert len(chunks[0].splitlines()) == 1
    assert sum(len(c.splitlines()) for c in chunks) == 3


def test_original_meta_field_survives_detail_envelope(api):
    original = item()
    original["_meta"] = {"from_source": ["original", None]}
    assert put(api, [original]).json()["status"] == "applied"
    detail = api.get("/api/runs/edge/objects/a").json()
    assert detail["object"] == original
    assert detail["meta"]["type_name"] == "leaf"


def test_large_subtree_uses_bounded_sql_parameters(api, monkeypatch):
    import contextlib
    import sqlite3

    store = api.app.state.store
    connect = store.connect

    @contextlib.contextmanager
    def limited():
        with connect() as conn:
            conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 512)
            yield conn

    monkeypatch.setattr(store, "connect", limited)
    response = api.post(
        "/ingest",
        json={
            "kind": "types",
            "test_id": "edge",
            "revision": 2,
            "changes": [
                {
                    "op": "create",
                    "node": {"type_id": i, "parent_id": 1, "name": f"type{i}"},
                }
                for i in range(3, 603)
            ],
        },
    )
    assert response.json()["status"] == "applied"
    assert put(api, [item()]).json()["status"] == "applied"
    listing = api.get("/api/runs/edge/objects?type_id=1")
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 1
    export = api.get("/api/runs/edge/export.ndjson?type_id=1")
    assert export.status_code == 200
    assert len(export.text.splitlines()) == 1


@pytest.mark.parametrize("run", ["a/b", ".", "..", "a\\b"])
def test_unaddressable_run_ids_rejected_before_ack(api, run):
    response = api.post(
        "/ingest",
        json={
            "kind": "types",
            "test_id": run,
            "revision": 1,
            "changes": [
                {"op": "create", "node": {"type_id": 1, "parent_id": 0, "name": "root"}}
            ],
        },
    )
    assert response.status_code == 422
    assert all(row["test_id"] != run for row in api.get("/api/runs").json()["items"])
