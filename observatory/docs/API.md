# Shared API contract
All JSON APIs same origin, UTF-8. test_id path segments encoded; slash, backslash and standalone dot/dot-dot segments are rejected before ACK. Application port 8000.

- POST /ingest: generator envelope unchanged. Response {status: applied|duplicate|quarantined|conflict, message_id, reason?}; only after FULL transaction commit. 503/429 for inability to persist/overload, 413 too large.
- GET /api/health: {status,sqlite_version,journal_mode,synchronous}
- GET /api/runs: {items:[{test_id,created_at,updated_at,object_count,message_count,duplicate_count,quarantined_count,conflict_count,revision,received_objects,applied_objects}]}, newest first
- GET /api/runs/{run}/metrics: run fields plus {rate_objects_per_second,rate_messages_per_second,database_bytes,storage_limit_bytes,backlog:0,frames:[{frame_id,frame_kind,unit,count}],categories:[{type_id,name,count}],recent_messages:[{id,kind,message_key,status,reason,received_at,object_count}],uptime_seconds}
- GET /api/runs/{run}/types: {revision,items:[{type_id,parent_id,name,object_count,subtree_count}],changes:[{revision,changes,received_at}]} (flat tree, counts optional)
- GET /api/runs/{run}/objects?limit=50&cursor=&type_id=&descendants=true&name_prefix=&object_id=&frame_id=&frame_kind=&unit=: {items:[{row_id,id,name,type_id,type_name,sequence,timestamp_ms,position}],next_cursor:null|string,snapshot_max:number}. Stable ascending keyset; optional snapshot_max freezes appended rows. filters shared by points/export.
- GET /api/runs/{run}/objects/{object_id}: {object:<complete unchanged original object>,meta:{row_id,tree_revision,received_at,type_name}}
- GET /api/runs/{run}/frames: {items:[{frame_id,frame_kind,unit,count}]}
- GET /api/runs/{run}/points?frame_id=...&frame_kind=...&unit=...&limit=3000 (+ same filters): {items:[{id,name,type_id,x,y,z}],frame:{frame_id,frame_kind,unit},limit,sampled:true,total:number}. Explicit single frame required, max5000.
- GET /api/runs/{run}/export.ndjson (+ same filters): bounded streaming full original object per line. Capture upper row ID at export start; chunked short-lived reads. Limit concurrent exports. Content-Disposition filename.
- GET /api/runs/{run}/messages?status=&limit=50: {items:[{id,kind,message_key,status,reason,received_at,object_count}]}
- GET /api/runs/{run}/messages/{id}: message metadata plus raw original JSON/string for diagnostics.

No synthetic product metrics. Changed existing object payload quarantines whole message pending semantics, never sequence-as-version. Category revisions must be contiguous; gaps durably quarantined and visible. Fully quarantined messages count as durably saved, not applied. Duplicate requests increase duplicate counter, do not double count applied objects. JSON hashes canonicalized; originals preserved.
