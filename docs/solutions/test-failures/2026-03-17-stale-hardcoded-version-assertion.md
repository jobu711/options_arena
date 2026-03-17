---
title: "Test asserts hardcoded version after switching to dynamic version"
date: 2026-03-17
module: options_arena.api
problem_type: test_failures
severity: medium
symptoms:
  - "test_create_app_returns_fastapi_instance fails with AssertionError"
  - "app.version == '1.5.0' assertion fails after version bump"
  - "Version mismatch between pyproject.toml and test expectations"
tags:
  - version
  - hardcoded
  - dynamic-import
  - test-assertion
root_cause: "app.py switched from hardcoded version string to dynamic __import__('options_arena').__version__, but test still asserted the old hardcoded value"
---

## Problem

`test_create_app_returns_fastapi_instance` in `tests/unit/api/test_app.py` asserted
`app.version == "1.5.0"`. When `app.py` was changed to dynamically retrieve the version
via `__import__("options_arena").__version__` (pulling from `pyproject.toml` which was
at `"2.10.0"`), the test silently became stale and would fail on execution.

## Root Cause

When changing from a hardcoded value to a dynamic source, the corresponding test
assertion was not updated. The test continued to check the old hardcoded string
instead of verifying against the same dynamic source.

## Solution

Changed the test assertion to use the same dynamic resolution:

```python
# BEFORE — hardcoded, breaks on every version bump
assert app.version == "1.5.0"

# AFTER — dynamic, always matches pyproject.toml
assert app.version == __import__("options_arena").__version__
```

## Prevention Rule

1. **When switching from hardcoded to dynamic values, grep for all test assertions
   that reference the old value** — `grep -rn '"1.5.0"' tests/` would have caught this.
2. **Version assertions should always be dynamic** — never hardcode a version string
   in a test. Assert against the authoritative source (`__version__`, `pyproject.toml`).
3. **After any `app.py` factory change, run `pytest tests/unit/api/test_app.py`** to
   verify the app factory tests still pass.

## Related

- `src/options_arena/api/app.py:187` — dynamic version via `__import__`
- `tests/unit/api/test_app.py:15` — the stale assertion
- PR #572 — CodeRabbit caught this during release review
