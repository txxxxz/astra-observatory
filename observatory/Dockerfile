# syntax=docker/dockerfile:1
# Runtime image digest is multi-platform; Compose fixes linux/arm64.
ARG PYTHON_IMAGE=python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
FROM node:22.14.0-bookworm-slim@sha256:1c18d9ab3af4585870b92e4dbc5cac5a0dc77dd13df1a5905cea89fc720eb05b AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM ${PYTHON_IMAGE} AS sqlite-build
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /build
# SQLite 3.51.3 contains the WAL-reset fix; verify the official source hash.
RUN python - <<'PY'
import hashlib, urllib.request, zipfile, io
url='https://www.sqlite.org/2026/sqlite-amalgamation-3510300.zip'
blob=urllib.request.urlopen(url, timeout=120).read()
with zipfile.ZipFile(io.BytesIO(blob)) as z:
    source=z.read('sqlite-amalgamation-3510300/sqlite3.c')
    assert hashlib.sha3_256(source).hexdigest() == '32d5424f97e0a7fc5ed2f6335afbb58be4e0298bd7117a34e39d345ff13d859e', 'SQLite source hash mismatch'
    open('sqlite3.c','wb').write(source)
PY
RUN gcc -O2 -fPIC -shared -DSQLITE_THREADSAFE=1 -DSQLITE_ENABLE_FTS5 -DSQLITE_ENABLE_RTREE -DSQLITE_ENABLE_COLUMN_METADATA -Wl,-soname,libsqlite3.so.0 -o libsqlite3.so.0 sqlite3.c -lm -ldl -lpthread

FROM ${PYTHON_IMAGE} AS runtime-deps
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    LD_LIBRARY_PATH=/opt/sqlite \
    OBS_DB_PATH=/data/observatory.db OBS_STATIC_DIR=/app/frontend/dist \
    OBS_STORAGE_LIMIT_BYTES=20401094656 OBS_MAX_BODY_BYTES=8388608 OBS_INGEST_CONCURRENCY=8
WORKDIR /app
COPY --from=sqlite-build /build/libsqlite3.so.0 /opt/sqlite/libsqlite3.so.0
COPY backend/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock && python -c "import sqlite3; assert sqlite3.sqlite_version == '3.51.3', sqlite3.sqlite_version; print('Patched SQLite:', sqlite3.sqlite_version)"
FROM runtime-deps AS runtime
COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist/
RUN useradd --uid 10001 --create-home observer && mkdir -p /data && chown observer:observer /data
USER observer
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "64", "--timeout-keep-alive", "5", "--no-access-log"]
