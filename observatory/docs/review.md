# Independent backend review · 2026-11-05

Scope: `docs/API.md`, `docs/design.md`, `backend/app.py`, `backend/store.py`, tests, Dockerfile/Compose and replay/benchmark/recovery scripts. Initial findings refer to the pre-fix source reviewed around 11:05 Asia/Shanghai. A targeted follow-up verified all four backend fixes and independently reran all 33 tests successfully. Implementation was not edited by the reviewer.

## Resolution verification

All four initial backend findings are **resolved** in the reviewed source:

- Export chooses rows using UTF-8 payload byte lengths, caps normal chunks at 1 MiB, and emits a larger individual object alone. Payload rows are fetched only for that bounded selection, and the connection closes before yielding. Regression tests check multibyte payloads, complete output and oversized single-row isolation.
- Subtree membership uses one JSON-array bind with `json_each`, retaining the frozen export category set. A regression lowers SQLite's bind limit to 512 and successfully lists/exports a 602-node tree.
- Detail now returns `{object, meta}`. The original object's `_meta` survives unchanged; frontend consumers and recovery/benchmark scripts use the new envelope.
- Slash, backslash and dot-segment run IDs return 422 before a run is inserted. Four parameterized cases verify this.

Independent follow-up: `/opt/miniconda3/envs/dev/bin/python -m pytest -q tests` → **33 passed in 1.45 seconds**. No unresolved critical backend issue was found within this targeted follow-up.

## Findings

1. **P1 — Export chunks are bounded by rows, not bytes** (`backend/store.py:681–695`). An object can occupy almost the 8 MiB request limit. Fetching 200 payloads, joining strings and encoding the chunk requires roughly three copies; one valid near-limit chunk can exceed the 4 GiB container limit, and two exports are admitted. Safe reproduction with 200 objects containing 64 KiB ASCII attributes yielded a 13,129,616-byte chunk and 39,429,696-byte Python allocation peak. Fix: bound chunk payload bytes, allowing at most one oversized object, and release DB reads before yielding. Root has accepted this finding and is implementing a fix.

2. **P2 — Accepted taxonomy size exceeds SQL parameter capacity** (`backend/store.py:318`, `541–561`). A subtree is expanded into one bind parameter per type although 100,000 types are accepted. With SQLite's 32,766-variable limit, four valid revisions creating 9,000 types each all apply, then listing the root subtree raises `OperationalError: too many SQL variables`; points and export use the same filter. The local Python SQLite limit is 250,000 and therefore masks this target-build issue. Reproduction used `Connection.setlimit(SQLITE_LIMIT_VARIABLE_NUMBER, 32766)`; the Docker build does not override the upstream variable-limit default, but runtime verification remains with the root agent because this review's Docker socket access was denied. Fix: use a recursive subquery for live membership, or one JSON array parameter with `json_each` for frozen membership.

3. **P2 — Detail replaces an unknown original property** (`backend/store.py:626–630`). An object with `_meta: {"original": "must survive"}` is accepted and preserved in raw messages/export, but object detail replaces that property with system metadata. This contradicts the complete-original-object detail contract. Fix: separate system metadata from the original payload, or preserve an existing original `_meta` and document how system metadata is exposed in that case.

4. **P2 — Accepted slash-containing run IDs cannot be queried** (`backend/store.py:162`; run-scoped routes in `backend/app.py`). A types message with `test_id="a/b"` applies and appears in `/api/runs`, but `/api/runs/a%2Fb/metrics` returns 404 because the decoded slash does not match `{run}`. All run-scoped operations share the problem. Fix: validate/document a path-safe run-ID restriction before acknowledging ingestion, or use an identifier transport that supports such values.

## Validation and limits

- `/opt/miniconda3/envs/dev/bin/python -m pytest -q tests`: **25 passed** in 1.02 seconds.
- Existing tests cover canonical retry/conflict handling, whole-message quarantine, unknown fields, create/rename/move rollback, same-frame filtering, frozen export row/category membership, commit failure, cancelled ingestion admission, and streaming lease release.
- Read inspection confirms original raw data and projection/quarantine commit within one transaction before acknowledgement; the writer lock serializes ingestion, and export closes each read before yielding.
- Additional temporary-database probes reproduced all four findings above; no production data or implementation files were changed.
- This review does not establish host power-loss durability or actual 20 GiB saturation behavior. Root owns deployed browser/runtime verification.

## Frontend source follow-up

Source inspection found two P2 state-consistency issues and reported them to the frontend owner: changing coordinate frame retained old points while updating the frame/unit label; taxonomy revisions updated the tree but did not refetch selected-subtree list/point membership.

Both fixes were subsequently **verified in source** (`frontend/src/App.tsx:242–344`): each points request clears prior points/count, a selected category's taxonomy revision resets pagination/snapshot and triggers list/point requests, and clearing selection resets pending detail state. The frontend owner reported a successful build (`index-Xps63x3y.js`); deployed browser interaction checks remain with root. No unresolved finding remains from this review's backend and targeted frontend scope.
