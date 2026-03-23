---
title: "Eval harness: 6 audit patterns — path traversal, UPSERT, pass@k math, type mismatch"
date: 2026-03-23
module: options_arena.evals
problem_type: pydantic_patterns
severity: critical
symptoms:
  - "Path traversal via unvalidated fixture path in EvalDefinition.market_context_fixture"
  - "INSERT OR REPLACE breaks FK constraints when child rows exist"
  - "pass@1 and pass@3 computed identically — pass@3 meaningless"
  - "grade_recommendation checks len(str) instead of content quality"
  - "Exception strings leak file paths into API responses"
  - "Sync file I/O blocks asyncio event loop in FastAPI context"
tags:
  - security
  - path-traversal
  - sqlite-upsert
  - pass-at-k
  - type-mismatch
  - exception-sanitization
  - async-blocking
root_cause: "New eval module shipped without security review; 7-agent audit caught 26 findings"
---

## Problem

The eval harness module (`evals/`) shipped with 26 audit findings across 7 agents.
The most critical:

1. **Path traversal**: `EvalDefinition.market_context_fixture` accepted arbitrary
   strings including `../../etc/passwd`. Runner read files without confinement.
2. **FK-breaking UPSERT**: `INSERT OR REPLACE` on `eval_definitions` is DELETE+INSERT
   in SQLite, breaking FK constraints to `eval_runs` child table.
3. **Wrong pass@k math**: Both `_compute_pass_at_1` and `_compute_pass_at_3` computed
   the same metric (any success across all k attempts), making pass@3 meaningless.
4. **Type mismatch**: `grade_recommendation` called `len(entry_criteria)` but
   `PositionRecommendation.entry_criteria` is `str` not `list[str]` — `len()` counted
   characters, so the check always passed.
5. **Exception leakage**: Raw `str(exc)` serialized into `EvalRun.details` and served
   via API, leaking file paths and schema details.
6. **Sync I/O blocking**: `Path.read_text()` called from async `run_eval_check()`,
   blocking the event loop in FastAPI context.

## Root Cause

Each issue had a distinct root cause:

1. No `field_validator` on `market_context_fixture` + no `is_relative_to()` check
2. SQLite `INSERT OR REPLACE` semantics misunderstood — it's DELETE+INSERT, not UPDATE
3. `EvalRun.passed` set from `successes >= 1` (across all k), not first attempt
4. Assumed `entry_criteria` was `list[str]` without checking model definition
5. Used `str(exc)` directly — no sanitization helper
6. Called sync functions from async without `asyncio.to_thread()`

## Solution

1. Added `field_validator` rejecting `..`, absolute paths, null bytes. Runner uses
   `is_relative_to(_PROJECT_ROOT)` confinement.
2. Replaced with `INSERT INTO ... ON CONFLICT(name) DO UPDATE SET ...` (proper UPSERT).
3. Tracked `first_attempt_passed` separately. Implemented combinatorial pass@k formula
   using `math.comb(n-c, k) / math.comb(n, k)`.
4. Changed to `len(entry_criteria.strip()) >= 20` for meaningful content check.
5. Created `_sanitize_error(exc)` that strips project root paths and truncates to 200 chars.
6. Wrapped grading loop in `asyncio.to_thread()`.

Additional fixes: match default case, `OutcomeRecord` validation, `GraderCheck` dataclass
replacing raw dicts, LIMIT on unbounded queries, mkdir before Database in CLI, narrowed
exception types, removed dead `save_baseline()` code.

## Prevention Rule

When creating a new module:
- Run `/full-audit` before merge — the 7-agent parallel audit catches issues no single
  reviewer would find.
- Every file path field needs a `field_validator` rejecting traversal (`..`, absolute, null bytes).
- SQLite UPSERT must use `ON CONFLICT DO UPDATE`, never `INSERT OR REPLACE` when FK children exist.
- When computing pass@k, track first-attempt results separately from aggregate successes.
- Always check the actual type of fields you're calling `len()` on — `str` vs `list[str]`.
- Every exception serialized for API consumption must go through a sanitization helper.
- Every sync I/O in an async function must use `asyncio.to_thread()`.

## Related

- `.claude/audits/FULL_AUDIT.md` — consolidated 26-finding audit report
- `docs/solutions/integration-issues/2026-03-17-joblib-path-traversal.md` — prior path traversal fix
- `docs/solutions/async-bugs/` — async pattern solutions
