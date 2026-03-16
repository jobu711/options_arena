---
title: "WebSocket connection counter TOCTOU race and queue leak"
date: 2026-03-16
module: options_arena.api.ws
problem_type: async_bug
severity: critical
symptoms:
  - "WebSocket connection count exceeds MAX_WS_CONNECTIONS_PER_TYPE under concurrent connects"
  - "scan_queues/debate_queues/batch_queues grow unbounded after client disconnects"
  - "Memory leak from orphaned asyncio.Queue instances"
tags:
  - websocket
  - toctou
  - race-condition
  - asyncio-lock
  - queue-leak
  - memory-leak
root_cause: "Check-then-increment on connection counter was non-atomic; queue cleanup missing from finally blocks"
---

## Problem

Three WebSocket endpoints (`ws_scan_progress`, `ws_debate_progress`, `ws_batch_progress`)
each maintained a connection counter (`_scan_ws_count`, etc.) with a max limit. The
check-and-increment pattern was:

```python
# TOCTOU race — two coroutines can pass the check simultaneously
if _scan_ws_count >= _MAX_WS_CONNECTIONS_PER_TYPE:
    await websocket.close(...)
    return
_scan_ws_count += 1
```

Two concurrent `await websocket.accept()` calls could both pass the check before either
incremented, exceeding the limit. Additionally, `scan_queues.pop()` was missing from
`finally` blocks, causing orphaned `asyncio.Queue` instances to accumulate.

## Root Cause

1. **TOCTOU race**: `asyncio` coroutines yield at every `await`. Between checking the
   counter and incrementing it, another coroutine can run and also pass the check.
2. **Queue leak**: The `finally` block decremented the counter but never removed the
   queue entry from the module-level dict (`scan_queues`, `debate_queues`, `batch_queues`).

## Solution

Added `asyncio.Lock` per endpoint type for atomic check-then-increment:

```python
_scan_ws_lock = asyncio.Lock()

reserved = False
async with _scan_ws_lock:
    if _scan_ws_count >= _MAX_WS_CONNECTIONS_PER_TYPE:
        await websocket.close(code=1013, reason="Too many connections")
        return
    _scan_ws_count += 1
    reserved = True

await websocket.accept()
try:
    # ... handle messages ...
finally:
    if reserved:
        async with _scan_ws_lock:
            _scan_ws_count -= 1
    scan_queues.pop(scan_id, None)  # cleanup queue
```

Key details:
- `reserved` flag tracks whether counter was incremented (for safe cleanup)
- Lock scope is minimal (just the check+increment, not the entire handler)
- Queue cleanup in `finally` prevents memory leaks on any exit path

## Prevention Rule

**Every shared mutable counter in async code needs an `asyncio.Lock`.** Check-then-act
on module-level state is always a TOCTOU race in async code. Also: every entry added to
a module-level dict in a handler MUST have a corresponding `.pop()` in the `finally` block.

## Related

- PR #555 (CodeRabbit review)
- `docs/solutions/async-bugs/2026-03-13-to-thread-precall.md`
