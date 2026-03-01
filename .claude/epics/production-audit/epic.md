---
name: production-audit
status: backlog
created: 2026-03-01T12:42:29Z
progress: 0%
prd: .claude/prds/production-audit.md
github: https://github.com/jobu711/options_arena/issues/169
---

# Epic: production-audit

## Overview

Remediate all 29 findings from the v2.1.0 production audit to achieve unconditional
production-ready status. Two HIGH findings (SecretStr for API keys, NaN bypassing pricing
validators) are blockers. The remaining 27 findings span input validation, reliability,
CI coverage, operational hardening, and architecture improvements. Seven of the 29 are
acceptable/won't-fix and require only documentation or trivial defensive code.

## Architecture Decisions

- **SecretStr for API keys**: Use `pydantic.SecretStr` on all API key config fields. Callers
  use `.get_secret_value()` at point of use. Automatic redaction in `repr()`, `model_dump()`,
  logs, and tracebacks.
- **Ticker validation**: Pydantic `Field(pattern=...)` on API request models + `mode="before"`
  uppercase validator. Applied at API boundary only — internal code trusts validated input.
- **MarketContext persistence**: Store as JSON blob column in `ai_theses` table (nullable for
  backward compatibility). New migration 009.
- **Windows log rotation**: Replace `RotatingFileHandler` with `QueueHandler` + `QueueListener`
  pattern (stdlib, no new dependency). Falls back gracefully.
- **CI frontend gates**: Add job to existing `.github/workflows/ci.yml` — `npm ci`, `vue-tsc`,
  `npm run build`. No separate workflow.
- **Rate limiting**: `slowapi` middleware on API routes. Per-IP, generous limits for loopback use.
- **Structured logging**: `python-json-logger` as optional JSON mode. Existing text mode unchanged.
- **Disclaimer removal**: Remove all disclaimer text and rendering. Single clean cut.

## Pre-Implementation Notes

Codebase exploration revealed two findings are already resolved:
- **AUDIT-011** (indicator weights sum to 1.05): Weights in `scoring/composite.py` already sum
  to 1.00. Task reduces to adding a module-level assertion guard.
- **AUDIT-010** (dual disclaimer definitions): Disclaimer is already centralized in
  `reporting/debate_export.py`. Task reduces to removing it entirely per PRD.

## Implementation Strategy

Seven tasks executed in dependency order. Tasks 1-2 are blockers (HIGH findings). Tasks 3-5
can run in parallel after blockers. Task 6 depends on tasks 3-5 being stable. Task 7 is
independent cleanup.

### Dependency Graph
```
Task 1 (SecretStr + NaN) ──┐
Task 2 (Input validation) ─┼──→ Task 3-5 (parallel) ──→ Task 6 (Architecture)
                           │
                           └──→ Task 7 (Cleanup, independent)
```

## Task Breakdown

### Task 1: SecretStr Migration + NaN/Inf Pricing Guards
**Findings**: AUDIT-001 (HIGH), AUDIT-005, AUDIT-006
**Effort**: S-M

SecretStr:
- [ ] Change `fred_api_key`, `groq_api_key` in `ServiceConfig` and `api_key` in `DebateConfig`
      from `str | None` to `SecretStr | None` (`models/config.py`)
- [ ] Update callers: `services/fred.py`, `services/health.py`, `agents/model_config.py`,
      `agents/orchestrator.py` — use `.get_secret_value()`
- [ ] Update `pydantic-settings` env parsing (SecretStr reads from env natively)
- [ ] Tests: `repr()` and `model_dump()` redact keys; `.get_secret_value()` returns plaintext

NaN/Inf:
- [ ] Add `math.isfinite()` checks to `validate_positive_inputs()` in `pricing/_common.py`
      before positivity checks
- [ ] Add `math.isfinite(sigma)` guard in `american_greeks()` in `pricing/american.py`
- [ ] Tests: NaN and Inf inputs raise `ValueError` with descriptive messages

### Task 2: API Input Validation + Security Hardening
**Findings**: AUDIT-003, AUDIT-025, AUDIT-024
**Effort**: S

- [ ] Add ticker validation to API request models: `Field(min_length=1, max_length=10,
      pattern=r"^[A-Z0-9.\-^]{1,10}$")` + `mode="before"` uppercase validator
- [ ] Add bounds to batch limits and list lengths in API request models
- [ ] Add `html.escape()` in `reporting/debate_export.py` before embedding markdown in
      PDF `<pre>` tags
- [ ] Add WebSocket `Origin` header validation in `api/ws.py` — accept only loopback origins
      (`127.0.0.1`, `localhost`, `[::1]`)
- [ ] Tests: rejected tickers, escaped HTML, blocked origins

### Task 3: MarketContext Persistence + Export Fix
**Findings**: AUDIT-008, AUDIT-011
**Effort**: M

- [ ] Create migration 009: add nullable `market_context_json` column to `ai_theses` table
- [ ] Update `data/repository.py` to persist `MarketContext` as JSON when saving debate results
- [ ] Update export path in `reporting/debate_export.py` to reconstruct `MarketContext` from
      stored JSON — render real prices instead of `$0.00`
- [ ] Add module-level assertion in `scoring/composite.py`:
      `assert abs(sum(INDICATOR_WEIGHTS.values()) - 1.0) < 1e-9`
- [ ] Tests: round-trip persist/load MarketContext, export with real prices

### Task 4: Reliability + Silent Failure Fixes
**Findings**: AUDIT-007, AUDIT-009, AUDIT-010, AUDIT-013, AUDIT-014
**Effort**: S-M

- [ ] AUDIT-007: Replace `lock.locked()` pre-check with atomic try-acquire pattern
      (`asyncio.wait_for(lock.acquire(), timeout=0.0)` → `TimeoutError` → 409)
- [ ] AUDIT-009: Add try/catch with `errors.value.push()` in `fetchScans()` in
      `web/src/stores/scan.ts`
- [ ] AUDIT-010: Remove all disclaimer text from `reporting/debate_export.py` and any
      rendering paths in `cli/commands.py`
- [ ] AUDIT-013: Replace `RotatingFileHandler` with `QueueHandler` + `QueueListener` in
      `cli/app.py` for Windows compatibility
- [ ] AUDIT-014: Move `scan_counter`, `active_scans`, `scan_queues` (and debate equivalents)
      to `create_app()` lifespan handler in `api/app.py`
- [ ] Tests: lock contention returns 409, app state initialized at startup

### Task 5: CI + Ops Hardening
**Findings**: AUDIT-002, AUDIT-020, AUDIT-018
**Effort**: S

- [ ] Add frontend CI job to `.github/workflows/ci.yml`: `npm ci`, `vue-tsc --noEmit`,
      `npm run build`
- [ ] Add `pip-audit` step to CI workflow (or `uv` equivalent)
- [ ] AUDIT-018: Add `rate_fetched_at` timestamp to FRED cache. Log warning when serving
      a rate older than 48h in `services/fred.py`
- [ ] Tests: FRED staleness warning at 48h boundary

### Task 6: Architecture Hardening
**Findings**: AUDIT-019, AUDIT-004, AUDIT-012, AUDIT-021
**Effort**: M-L

- [ ] AUDIT-019: Add missing validators to `Quote` (price/bid/ask positivity + finite),
      `OptionContract` (strike/bid/ask/last + volume/OI non-negative),
      `WatchlistTickerDetail`/`HistoryPoint` (composite_score [0,100]),
      `ScanConfig` (top_n/ohlcv_min_bars minimum bounds)
- [ ] AUDIT-004: Add `slowapi` middleware for per-IP rate limiting. `uv add slowapi`
- [ ] AUDIT-012: Add `python-json-logger` for optional JSON logging mode. `uv add python-json-logger`.
      Add `scan_id` and `ticker` fields via `LoggerAdapter` or `extra={}`
- [ ] AUDIT-021: Replace explicit batching in Phase 3 with semaphore-bounded
      `asyncio.gather()` over all top-N tickers (or increase `options_batch_size` default)
- [ ] Tests: validator rejection, rate limit 429 responses

### Task 7: Low-Priority Cleanup + Documentation
**Findings**: AUDIT-015, AUDIT-016, AUDIT-017, AUDIT-022, AUDIT-023, AUDIT-026, AUDIT-027,
             AUDIT-028, AUDIT-029
**Effort**: S

- [ ] AUDIT-015: Document single debate no-lock as intentional (code comment)
- [ ] AUDIT-017: Document direction thresholds as standard TA defaults (config docstring)
- [ ] AUDIT-026: Add defensive try/except around `websocket.close()` calls in `api/ws.py`
- [ ] AUDIT-027: Sync operation store from API health endpoint on page load in Vue
- [ ] AUDIT-028: Add 30s default timeout via `AbortController` in `web/src/composables/useApi.ts`
- [ ] AUDIT-029: Add `test_exceptions.py` with `isinstance` checks for exception hierarchy
- [ ] AUDIT-016, AUDIT-022, AUDIT-023: No code changes needed (documented as acceptable)

## Dependencies

### New Packages
| Package | Task | Purpose |
|---------|------|---------|
| `slowapi` | 6 | Per-IP API rate limiting |
| `python-json-logger` | 6 | Structured JSON logging |

### DB Migration
- Migration 009: nullable `market_context_json` TEXT column on `ai_theses` (Task 3)

### Existing Infra
- CI workflow (`.github/workflows/ci.yml`) — extended, not replaced
- SQLite migration runner — existing pattern in `data/migrations/`

## Success Criteria (Technical)

- All 2,454 Python tests + 38 E2E tests pass
- `mypy --strict` zero errors
- `ruff check .` zero errors
- `vue-tsc --noEmit` + `npm run build` pass in CI
- `repr(settings)` and `model_dump()` show `'**********'` for API keys
- `validate_positive_inputs(float("nan"), ...)` raises `ValueError`
- Ticker inputs matching `^[A-Z0-9.\-^]{1,10}$` accepted; all others rejected with 422
- Export renders actual prices from persisted MarketContext
- +50 new tests minimum

## Estimated Effort

- **Tasks 1-2** (blockers): ~1 day
- **Tasks 3-5** (parallel): ~2 days
- **Task 6** (architecture): ~2 days
- **Task 7** (cleanup): ~0.5 day
- **Total**: ~5-6 days
- **Critical path**: Tasks 1-2 → Tasks 3-5 → Task 6

## Tasks Created
- [ ] #174 - SecretStr Migration + NaN/Inf Pricing Guards (parallel: true, blocker)
- [ ] #175 - API Input Validation + Security Hardening (parallel: true, blocker)
- [ ] #176 - MarketContext Persistence + Export Fix (parallel: true, depends: #174, #175)
- [ ] #170 - Reliability + Silent Failure Fixes (parallel: true, depends: #174, #175)
- [ ] #171 - CI + Ops Hardening (parallel: true, depends: #174, #175)
- [ ] #172 - Architecture Hardening (parallel: false, depends: #176, #170, #171)
- [ ] #173 - Low-Priority Cleanup + Documentation (parallel: true, independent)

Total tasks: 7
Parallel tasks: 6
Sequential tasks: 1 (#172 — after #176, #170, #171 stabilize)
Estimated total effort: 34-46 hours
