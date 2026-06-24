# Debug: SSE Remote Archive [CLOSED]

## Session
- sessionId: sse-remote-archive
- scope: Trae remote SSE requests not appearing in admin stats/training archive

## Confirmed Root Causes
1. Desensitized chat requests were archived with `action_taken=desensitized`, but training persistence only accepted `passed`.
2. When an SSE client actively closed the connection after receiving early chunks, cancellation could interrupt the stream `finally` block before `_write_chat_archive` ran because archive happened after awaited cleanup/debug work.

## Fixes Kept
- `storage/training.py`: `_is_training_candidate` now accepts both `passed` and `desensitized`, while still excluding blocked requests.
- `proxy/relay.py`: streaming archive payload is built and enqueued before awaited client cleanup, so early client disconnects still archive collected stream content.
- `.gitignore`: `data/` is ignored to avoid tracking PostgreSQL runtime files.

## Verification
- Public SSE normal request wrote successfully.
- Public SSE desensitized request wrote successfully and latest DB row has `is_desensitized=t`.
- Simulated early stream close after reading first SSE bytes wrote successfully.
- Admin stats after final verification: `today_requests=6`, `total_requests=7`.

## Cleanup
- Runtime debug instrumentation removed from application code.
- Debug server stopped.
- Debug record retained for handoff/reference.

## Status
- CLOSED
