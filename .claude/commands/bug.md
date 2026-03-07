---
allowed-tools: Read, Glob, Grep, Edit, Write, Bash, Agent, mcp__context7__resolve-library-id, mcp__context7__query-docs
---

# Bug Fix

Fix a bug with surgical precision using Context7 to verify library APIs.

## Usage
```
/bug <description of the bug or error message>
```

## Instructions

### 1. Reproduce & Locate

Based on the argument provided:

- **Error message** → Search for the code that produces it, trace the call stack
- **File + description** → Read the file, identify the broken logic
- **Vague description** → Search codebase for related code, narrow down

Read the affected file(s) and the relevant module CLAUDE.md before making changes.

### 2. Context7 Verification

If the bug involves an external library (yfinance, pydantic, httpx, scipy, pandas,
pydantic-ai, typer, rich, fastapi, aiosqlite, numpy), use Context7 to verify the API:

1. Call `resolve-library-id` with the library name
2. Call `query-docs` with the specific API question (return types, field names, signatures)
3. Compare documented behavior against what the code assumes

If Context7 reveals the code's assumption is wrong, fix the assumption — don't work around it.

### 3. Fix

Apply the minimal change that fixes the root cause:

- Do NOT refactor surrounding code, add docstrings, or "improve" unrelated things
- Respect project rules: typed models (not dicts), `X | None` (not `Optional`),
  `math.isfinite()` on numeric validators, UTC validators on datetime fields
- Check architecture boundaries (CLAUDE.md table) before adding imports

### 4. Verify

Run these in sequence:

1. **Tests**: `uv run pytest tests/unit/<module>/test_<file>.py -v`
   - If no test covers the bug, write one that would have caught it
2. **Lint + format**: `uv run ruff check . --fix && uv run ruff format .`
3. **Type check**: `uv run mypy src/options_arena/<module>/ --strict`

### 5. Report

Present results as:

```
Root Cause: <one sentence — what's wrong and why>
Fix: <what was changed>
Context7: <what was verified, or "N/A — no library involved">
Tests: <pass/fail + any new test added>
Lint/Types: <clean or issues found>
```

## Error Handling

- Can't reproduce → "Could not reproduce. Provide the full error traceback or steps."
- Root cause unclear → Report what was investigated, don't guess-fix
- Multiple possible causes → Fix the most likely, note alternatives

## Important Notes

- Change only what's necessary — nothing more
- Never suppress errors with bare `except:` or uncommented `# type: ignore`
- If the fix requires a model change, check for downstream consumers first
- If Context7 docs conflict with observed behavior, note the discrepancy
