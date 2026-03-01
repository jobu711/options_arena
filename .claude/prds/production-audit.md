---
name: production-audit
description: Fix all 29 findings from production audit — data correctness, security, reliability, ops, and architecture hardening
status: backlog
created: 2026-03-01T17:37:58Z
---

# PRD: production-audit

## Executive Summary

Options Arena v2.1.0 passed a comprehensive 7-layer production audit with a **CONDITIONAL GO** rating. The audit identified 29 findings (0 critical, 2 high, 12 medium, 15 low) across data integrity, reliability, security, performance, architecture, web UI, and operations. This PRD tracks remediation of all 29 findings to achieve an unconditional production-ready state. The two blockers (API key leakage via plaintext `str` fields, and NaN bypassing pricing validators) must be resolved first, followed by systematic hardening across all layers.

## Problem Statement

The production audit revealed several categories of issues:

1. **Data correctness gaps**: `NaN` can bypass pricing input validation in `validate_positive_inputs()` and `american_greeks()`, producing silently wrong Greeks that users make financial decisions on.
2. **Secret leakage risk**: API keys stored as `str` (not `SecretStr`) are exposed in logs, tracebacks, `model_dump()`, and debug output. Groq API key grants billing access.
3. **Input validation gaps**: API endpoints accept arbitrary-length ticker strings with no pattern validation, enabling resource waste and log pollution.
4. **Silent failures**: Export endpoint renders `$0.00` prices; `fetchScans()` store doesn't catch errors; Windows log rotation fails silently.
5. **CI coverage gap**: Frontend (Vue 3 + TypeScript) has zero CI gates — broken builds and type errors ship undetected.
6. **Operational gaps**: No structured logging, no dependency scanning, no FRED staleness warnings.
7. **Architecture debt**: Dual disclaimer definitions, indicator weights summing to 1.05, missing model validators, lazy `app.state` initialization.

These issues individually range from cosmetic to potentially dangerous. Together, they represent the gap between a well-architected prototype and a production-hardened tool.

## User Stories

### US-1: Developer maintaining the codebase
**As a** developer pushing code to Options Arena,
**I want** CI to catch frontend regressions and dependency vulnerabilities,
**so that** I don't ship broken TypeScript or known CVEs to users.

**Acceptance criteria:**
- `vue-tsc --noEmit` and `npm run build` run in CI on every push
- `pip-audit` or equivalent scans dependencies in CI
- CI fails on type errors, build failures, or known CVEs

### US-2: User running the tool locally
**As a** user running `options-arena serve` on Windows,
**I want** logs to rotate without errors and the API to validate my inputs,
**so that** I don't see stderr pollution or trigger unintended yfinance calls.

**Acceptance criteria:**
- No `PermissionError` from `RotatingFileHandler` on Windows
- Ticker inputs validated (1-10 chars, `^[A-Z0-9.\-^]{1,10}$`)
- Oversized or malformed payloads rejected with 422

### US-3: User exporting debate results
**As a** user exporting a past debate to markdown,
**I want** the exported report to contain the actual market prices from the debate,
**so that** the export is useful for review and record-keeping.

**Acceptance criteria:**
- MarketContext persisted alongside debate results in `ai_theses`
- Exported markdown shows real prices, not `$0.00`
- DB migration is backward-compatible (nullable new columns)

### US-4: Security-conscious user
**As a** user with a Groq API key configured,
**I want** my API key to never appear in logs, tracebacks, or debug output,
**so that** my billing credentials are protected.

**Acceptance criteria:**
- All API key fields use `SecretStr`
- `repr()`, `model_dump()`, and `str()` on config objects show `'**********'`
- Callers updated to use `.get_secret_value()` at point of use
- No API keys in `logs/options_arena.log` at any log level

### US-5: User relying on pricing accuracy
**As a** user making financial decisions based on computed Greeks,
**I want** the pricing engine to reject invalid inputs (NaN, Inf),
**so that** I never see plausible-looking but incorrect numbers.

**Acceptance criteria:**
- `validate_positive_inputs()` checks `math.isfinite()` before positivity
- `american_greeks()` checks `math.isfinite(sigma)` before proceeding
- NaN/Inf inputs raise `ValueError` with descriptive message
- Existing tests pass; new tests cover NaN/Inf edge cases

## Requirements

### Functional Requirements

#### Phase 1: Data Correctness + Security
| ID | Finding | Requirement | Effort |
|----|---------|-------------|--------|
| AUDIT-001 | API keys as `str` | Change `fred_api_key`, `groq_api_key`, `api_key` to `SecretStr \| None`. Update all callers (fred.py, health.py, model_config.py, orchestrator.py) to use `.get_secret_value()`. | S |
| AUDIT-005 | NaN bypasses `validate_positive_inputs()` | Add `math.isfinite()` checks before positivity checks in `pricing/_common.py`. | S |
| AUDIT-006 | Missing `isfinite()` in `american_greeks()` | Add `not math.isfinite(sigma)` guard at `pricing/american.py` sigma check. | S |
| AUDIT-003 | No ticker validation on API | Add `Field(min_length=1, max_length=10, pattern=r"^[A-Z0-9.\-^]{1,10}$")` to ticker fields. Add `mode="before"` uppercase validator. Add bounds to batch limits and list lengths. | S |
| AUDIT-025 | PDF export renders raw HTML | Use `html.escape(md_content)` before embedding in `<pre>` tag in `reporting/debate_export.py`. | S |
| AUDIT-011 | Indicator weights sum to 1.05 | Audit weights, normalize to 1.0. Add module-level assertion: `assert abs(sum(INDICATOR_WEIGHTS.values()) - 1.0) < 1e-9`. | S |

#### Phase 2: Reliability + Silent Failures
| ID | Finding | Requirement | Effort |
|----|---------|-------------|--------|
| AUDIT-008 | Export shows $0.00 prices | Persist `MarketContext` in `ai_theses` table via new DB migration. Reconstruct from stored data at export time. | M |
| AUDIT-010 | Dual disclaimer definitions | Remove all disclaimer text from `cli/rendering.py` and `reporting/debate_export.py`. Remove disclaimer rendering from all output paths. | S |
| AUDIT-007 | TOCTOU in batch debate lock | Replace `lock.locked()` pre-checks with atomic try-acquire pattern (e.g., `asyncio.wait_for(lock.acquire(), timeout=0.0)` with `TimeoutError` → 409). | S |
| AUDIT-009 | `fetchScans()` missing error handling | Add try/catch with `errors.value.push()` matching other store actions in `web/src/stores/scan.ts`. | S |
| AUDIT-013 | RotatingFileHandler Windows bug | Replace `RotatingFileHandler` with a Windows-compatible alternative (`concurrent_log_handler` or `QueueHandler` + `QueueListener`). | S |
| AUDIT-014 | `app.state` counters lazily initialized | Move `scan_counter`, `active_scans`, `scan_queues` (and debate equivalents) to `create_app()` lifespan handler. | S |

#### Phase 3: Ops + CI
| ID | Finding | Requirement | Effort |
|----|---------|-------------|--------|
| AUDIT-002 | No frontend CI gates | Add CI job: `npm ci`, `vue-tsc --noEmit`, `npm run build` in `.github/workflows/ci.yml`. | S |
| AUDIT-020 | No dependency audit | Add `pip-audit` or `uv pip audit` step to CI workflow. | S |
| AUDIT-018 | FRED rate staleness | Log warning when serving a FRED rate older than 48h. Add `rate_fetched_at` timestamp to cached value. | S |
| AUDIT-024 | WebSocket no Origin check | Add `Origin` header validation before `websocket.accept()` in `api/ws.py`. Accept only loopback origins. | S |

#### Phase 4: Architecture + Performance
| ID | Finding | Requirement | Effort |
|----|---------|-------------|--------|
| AUDIT-019 | Missing model validators | Add validators to: `Quote` (price/bid/ask positivity + finite), `OptionContract` (strike/bid/ask/last + volume/OI non-negative), `WatchlistTickerDetail`/`HistoryPoint` (composite_score [0,100]), `ScanConfig` (top_n/ohlcv_min_bars minimum bounds). | M |
| AUDIT-012 | Semi-structured logging | Add `python-json-logger` dependency. Add optional JSON logging mode. Add `scan_id` and `ticker` fields via `LoggerAdapter` or `extra={}`. | M |
| AUDIT-004 | No API rate limiting | Add `slowapi` package for per-IP rate limiting middleware on all API endpoints. | M |
| AUDIT-021 | Phase 3 sequential batching | Replace explicit batching with semaphore-bounded `asyncio.gather()` over all top-N tickers. Or increase `options_batch_size` default. | M |

#### Acceptable / Won't Fix
| ID | Finding | Disposition |
|----|---------|-------------|
| AUDIT-015 | Single debate no lock | Document as intentional (single debates are lightweight). |
| AUDIT-016 | `except BaseException` in rate limiter | Keep as-is (legitimate cleanup pattern, exception is re-raised). |
| AUDIT-017 | Direction thresholds not calibrated | Document that defaults are standard TA thresholds. Add config docstring note. |
| AUDIT-022 | Redundant ADX/supertrend computation | Low impact. Cache if convenient but not required. |
| AUDIT-023 | Row-by-row watchlist ops | Correct by design (single-row operations). |
| AUDIT-026 | WebSocket close in finally | Add defensive try/except around `websocket.close()` calls. |
| AUDIT-027 | Operation store not auto-synced | Sync from API health endpoint on page load. |
| AUDIT-028 | No default API request timeout | Add 30s default timeout via AbortController in `useApi.ts`. |
| AUDIT-029 | No exception hierarchy tests | Add small `test_exceptions.py` with isinstance checks. |

### Non-Functional Requirements

- **Backward compatibility**: All DB migrations must be additive (nullable columns). No breaking changes to CLI flags, API contracts, or config env vars.
- **Performance**: No measurable regression in scan pipeline time. Phase 3 optimization (AUDIT-021) should improve, not degrade.
- **Test coverage**: Every fix must include tests. NaN/Inf edge cases, SecretStr repr, ticker validation rejection, export with persisted MarketContext.
- **Windows compatibility**: All fixes must work on Windows 11 (primary dev platform). Especially AUDIT-013 (log rotation).
- **Dependency discipline**: New dependencies (`slowapi`, `python-json-logger`, `concurrent-log-handler` if needed) added via `uv add`. No manual pyproject.toml edits.

## Success Criteria

| Metric | Target |
|--------|--------|
| Audit findings resolved | 29/29 (including acceptable/won't-fix with documented rationale) |
| HIGH findings fixed | 2/2 (AUDIT-001, AUDIT-002) |
| MEDIUM findings fixed | 12/12 |
| New test count | +50 minimum (covering all fix verifications) |
| All existing tests pass | 2,454 Python + 38 E2E green |
| `mypy --strict` | Zero errors |
| `ruff check .` | Zero errors |
| Frontend CI | `vue-tsc` + `npm run build` pass |
| API key in logs | Zero occurrences of plaintext keys in any log output |
| NaN through pricing | `ValueError` raised for NaN/Inf S, K, sigma inputs |
| Production readiness score | All layers 4/5 or higher, overall UNCONDITIONAL GO |

## Constraints & Assumptions

### Constraints
- **No new frameworks**: Hardening only — no new feature work mixed in.
- **Migration compatibility**: SQLite migrations must be forward-only and additive.
- **Loopback assumption**: Security fixes (rate limiting, origin checks) assume loopback-only deployment. If the server is ever exposed publicly, a full security review is needed.
- **Groq-only**: SecretStr changes scoped to current Groq provider. Future LLM providers will need their own SecretStr handling.

### Assumptions
- `slowapi` is compatible with the current FastAPI version (>=0.133.1).
- `python-json-logger` works with the existing dual-handler logging setup.
- Persisting MarketContext as JSON blob in `ai_theses` is sufficient (no need for normalized columns).
- Removing disclaimers entirely is acceptable from a legal/compliance perspective.

## Out of Scope

- New features (additional LLM providers, real-time streaming, frontend unit tests)
- Performance optimization beyond AUDIT-021 (Phase 3 batching)
- Authentication/authorization (server is loopback-only by design)
- API versioning or breaking changes
- Backfilling MarketContext for existing debate records (only new debates get persisted context)
- Full security penetration testing

## Dependencies

### External
- `slowapi` package (AUDIT-004)
- `python-json-logger` package (AUDIT-012)
- Possibly `concurrent-log-handler` (AUDIT-013, if QueueHandler pattern is insufficient)

### Internal
- DB migration infrastructure (AUDIT-008 — MarketContext persistence)
- CI workflow file (AUDIT-002, AUDIT-020)
- All callers of API key fields (AUDIT-001 — 4 files minimum)

## Implementation Phases

### Phase 1: Data Correctness + Security (~1-2 days)
AUDIT-001, AUDIT-005, AUDIT-006, AUDIT-003, AUDIT-025, AUDIT-011
*Anything that could produce wrong financial data or leak secrets.*

### Phase 2: Reliability + Silent Failures (~1-2 days)
AUDIT-008, AUDIT-010, AUDIT-007, AUDIT-009, AUDIT-013, AUDIT-014
*Things that fail silently or mislead the user.*

### Phase 3: Ops + CI (~1 day)
AUDIT-002, AUDIT-020, AUDIT-018, AUDIT-024
*Operational hardening and CI coverage.*

### Phase 4: Architecture + Performance (~2-3 days)
AUDIT-019, AUDIT-012, AUDIT-004, AUDIT-021
*Structural improvements and performance optimization.*

### Phase 5: Low-Priority Cleanup (~0.5 days)
AUDIT-015 (document), AUDIT-017 (document), AUDIT-022, AUDIT-026, AUDIT-027, AUDIT-028, AUDIT-029
*Quick wins and documentation for acceptable findings.*

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| SecretStr breaks config loading | Medium | High | Test `AppSettings()` with and without env vars after change |
| MarketContext migration breaks existing data | Low | High | Nullable columns, no NOT NULL constraints |
| Weight normalization changes scoring results | Medium | Medium | Compare before/after on fixture data |
| slowapi conflicts with operation mutex | Low | Medium | Test concurrent requests with both active |
| Disclaimer removal breaks expected output | Low | Low | Update any tests asserting disclaimer text |

## Source Reference

All findings sourced from: `production_audit.md` (root of repository, untracked).
