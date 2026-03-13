---
title: "asyncio.to_thread pre-calls function instead of deferring execution"
date: 2026-03-13
module: options_arena.services
problem_type: async_bug
severity: critical
symptoms:
  - "Blocking call runs on main event loop thread instead of worker thread"
  - "Event loop freezes during yfinance/sync API calls"
  - "to_thread appears to have no effect — call still blocks"
tags:
  - asyncio
  - to_thread
  - blocking
  - yfinance
  - event-loop
root_cause: "Passing fn() instead of fn to asyncio.to_thread — pre-calls the function synchronously on the calling thread"
---

## Problem

When wrapping synchronous calls (e.g., yfinance) with `asyncio.to_thread`, the function
executes on the main event loop thread instead of a worker thread, blocking the entire
event loop.

## Root Cause

```python
# WRONG — fn() is called IMMEDIATELY on the current thread, result passed to to_thread
await asyncio.to_thread(yf.download("AAPL"))

# RIGHT — fn and args passed separately, to_thread calls fn(*args) in worker thread
await asyncio.to_thread(yf.download, "AAPL")
```

`to_thread(fn())` evaluates `fn()` first (synchronously on the calling thread), then
passes the return value to `to_thread` which does nothing useful with it. The parentheses
`()` after `fn` cause immediate invocation.

## Solution

Always pass the callable and its arguments separately to `to_thread`:

```python
# Correct patterns:
await asyncio.to_thread(fn, arg1, arg2)
await asyncio.to_thread(fn, arg1, kwarg=value)

# ServiceBase helper encapsulates this:
result = await self._yf_call(yf.download, "AAPL", period="1y")
```

## Prevention Rule

**Pass callable + args separately to `to_thread`.** Grep for `to_thread(.*())` to find
violations — the pattern `to_thread(something())` with parentheses inside is always wrong.

## Related

- `src/options_arena/services/base.py` — `_yf_call()` helper wraps `to_thread` correctly
- Python docs: `asyncio.to_thread(func, /, *args, **kwargs)`
