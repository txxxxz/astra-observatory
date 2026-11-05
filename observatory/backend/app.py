"""Same-origin HTTP ingestion, exploration API and built frontend."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from .store import CapacityError, InvalidMessage, Store


def filters(
    type_id: int | None = Query(None, ge=1),
    descendants: bool = True,
    name_prefix: str | None = Query(None, max_length=4096),
    object_id: str | None = Query(None, max_length=512),
    frame_id: str | None = Query(None, max_length=512),
    frame_kind: str | None = Query(None, max_length=512),
    unit: str | None = Query(None, max_length=512),
):
    return {
        "type_id": type_id,
        "descendants": descendants,
        "name_prefix": name_prefix,
        "object_id": object_id,
        "frame_id": frame_id,
        "frame_kind": frame_kind,
        "unit": unit,
    }


class LeaseStreamingResponse(StreamingResponse):
    """Release admission even when a streaming client disconnects or send fails."""

    def __init__(self, *args, release, **kwargs):
        super().__init__(*args, **kwargs)
        self.release = release

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.release()


def create_app(db_path=None, max_body_bytes=None, storage_limit_bytes=None):
    path = db_path or os.getenv("OBS_DB_PATH", "data/observatory.db")
    body_limit = (
        max_body_bytes
        if max_body_bytes is not None
        else int(os.getenv("OBS_MAX_BODY_BYTES", "8388608"))
    )
    storage_limit = (
        storage_limit_bytes
        if storage_limit_bytes is not None
        else int(os.getenv("OBS_STORAGE_LIMIT_BYTES", "20401094656"))
    )
    store = Store(path, storage_limit_bytes=storage_limit)
    app = FastAPI(title="Astra · 宇宙万物观测站", version="1.0.0")
    app.state.store = store
    app.state.pending_ingest = set()
    incoming = threading.BoundedSemaphore(int(os.getenv("OBS_INGEST_CONCURRENCY", "8")))
    exports = threading.BoundedSemaphore(int(os.getenv("OBS_EXPORT_CONCURRENCY", "2")))
    static_dir = Path(
        os.getenv(
            "OBS_STATIC_DIR", str(Path(__file__).resolve().parents[1] / "frontend/dist")
        )
    ).resolve()
    logger = logging.getLogger("observatory")
    if not logger.handlers:
        handler = RotatingFileHandler(
            store.path.parent / "observatory.log",
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)

    @app.exception_handler(KeyError)
    async def missing(_request, _exc):
        return JSONResponse({"detail": "Run or record not found"}, status_code=404)

    @app.exception_handler(sqlite3.Error)
    async def database_error(_request, exc):
        logger.error("Database operation failed: %s", type(exc).__name__)
        return JSONResponse(
            {"detail": "Database temporarily unavailable; message not acknowledged"},
            status_code=503,
            headers={"Retry-After": "2"},
        )

    @app.post("/ingest")
    async def ingest(request: Request):
        if not incoming.acquire(blocking=False):
            raise HTTPException(
                429,
                "Ingestion concurrency limit reached; retry later",
                headers={"Retry-After": "1"},
            )
        owns_slot = True
        try:
            length = request.headers.get("content-length")
            if length:
                try:
                    if int(length) > body_limit:
                        raise HTTPException(
                            413, "Message exceeds configured body limit"
                        )
                except ValueError:
                    raise HTTPException(400, "Invalid Content-Length")

            async def receive():
                chunks = []
                size = 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > body_limit:
                        raise HTTPException(
                            413, "Message exceeds configured body limit"
                        )
                    chunks.append(chunk)
                return b"".join(chunks)

            try:
                raw = await asyncio.wait_for(receive(), timeout=15)
            except TimeoutError:
                raise HTTPException(408, "Request body timeout; retry message")
            try:

                def reject_constant(value):
                    raise ValueError("Non-finite JSON number: " + value)

                data = json.loads(raw, parse_constant=reject_constant)
                if not isinstance(data, dict):
                    raise InvalidMessage("Message envelope must be an object")

                def persist():
                    try:
                        return store.ingest(data, raw)
                    finally:
                        incoming.release()

                task = asyncio.create_task(asyncio.to_thread(persist))
                app.state.pending_ingest.add(task)

                def finished(done):
                    app.state.pending_ingest.discard(done)
                    if not done.cancelled():
                        done.exception()  # consume failures even if the caller disconnected

                task.add_done_callback(finished)
                owns_slot = False  # the durable writer owns this slot until it finishes
                result = await asyncio.shield(task)
            except (
                InvalidMessage,
                ValueError,
                UnicodeDecodeError,
                RecursionError,
            ) as exc:
                raise HTTPException(422, str(exc)[:500])
            except CapacityError as exc:
                raise HTTPException(503, str(exc), headers={"Retry-After": "2"})
            except OSError:
                raise HTTPException(
                    503,
                    "Storage unavailable; message not acknowledged",
                    headers={"Retry-After": "2"},
                )
            return result
        finally:
            if owns_slot:
                incoming.release()

    @app.get("/api/health")
    def health():
        with store.connect() as conn:
            return {
                "status": "ok",
                "sqlite_version": sqlite3.sqlite_version,
                "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
                "synchronous": conn.execute("PRAGMA synchronous").fetchone()[0],
                "synchronous_name": "FULL",
                "storage_bytes": store.storage_bytes(),
                "storage_limit_bytes": store.storage_limit_bytes,
            }

    @app.get("/api/runs")
    def runs():
        return store.runs()

    @app.get("/api/runs/{run}/metrics")
    def metrics(run: str):
        return store.metrics(run)

    @app.get("/api/runs/{run}/types")
    def types(run: str):
        return store.types(run)

    @app.get("/api/runs/{run}/frames")
    def frames(run: str):
        return store.frames(run)

    @app.get("/api/runs/{run}/objects")
    def objects(
        run: str,
        f: Annotated[dict, Depends(filters)],
        limit: int = Query(50, ge=1, le=200),
        cursor: int = Query(0, ge=0),
        snapshot_max: int | None = Query(None, ge=0),
    ):
        return store.objects(run, f, limit, cursor, snapshot_max)

    @app.get("/api/runs/{run}/points")
    def points(
        run: str,
        f: Annotated[dict, Depends(filters)],
        limit: int = Query(3000, ge=1, le=5000),
    ):
        if any(f[k] is None for k in ("frame_id", "frame_kind", "unit")):
            raise HTTPException(
                422,
                "frame_id, frame_kind and unit are all required; coordinate frames cannot be mixed",
            )
        return store.points(run, f, limit)

    @app.get("/api/runs/{run}/export.ndjson")
    def export(
        run: str,
        f: Annotated[dict, Depends(filters)],
        snapshot_max: int | None = Query(None, ge=0),
    ):
        if not exports.acquire(blocking=False):
            raise HTTPException(
                429,
                "Two exports are already active; retry later",
                headers={"Retry-After": "2"},
            )
        released = False
        lock = threading.Lock()

        def release():
            nonlocal released
            with lock:
                if not released:
                    released = True
                    exports.release()

        try:
            snapshot = store.export_snapshot(run, f, snapshot_max)
        except BaseException:
            release()
            raise

        def stream():
            try:
                yield from store.export_chunks(snapshot)
            finally:
                release()

        filename = quote("astra-" + run + ".ndjson", safe="")
        return LeaseStreamingResponse(
            stream(),
            release=release,
            media_type="application/x-ndjson",
            headers={
                "Content-Disposition": f"attachment; filename=astra-export.ndjson; filename*=UTF-8''{filename}",
                "X-Snapshot-Max": str(snapshot[2]),
                "Cache-Control": "no-store",
                "X-Export-Semantics": "immutable-objects; frozen-row-upper-bound-and-category-set",
            },
            background=BackgroundTask(release),
        )

    @app.get("/api/runs/{run}/messages")
    def messages(
        run: str,
        limit: int = Query(50, ge=1, le=200),
        status: str | None = Query(None, pattern="^(applied|quarantined|conflict)$"),
    ):
        return store.messages(run, limit, status)

    @app.get("/api/runs/{run}/messages/{message_id}")
    def message(run: str, message_id: int):
        return store.message(run, message_id)

    @app.get("/api/runs/{run}/objects/{object_id:path}")
    def object_detail(run: str, object_id: str):
        return store.object(run, object_id)

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "API route not found")
        candidate = (static_dir / path).resolve()
        if candidate.is_relative_to(static_dir) and candidate.is_file():
            return FileResponse(candidate)
        index = static_dir / "index.html"
        if index.is_file():
            return FileResponse(index)
        if not path:
            return JSONResponse(
                {
                    "service": "Astra Observatory",
                    "frontend": "Build frontend with npm run build",
                    "docs": "/docs",
                }
            )
        raise HTTPException(404, "Frontend asset not found")

    return app


app = create_app()
