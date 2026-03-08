---
name: feature-alpha-audit
description: Codebase-wide feature audit scoring value vs. maintenance cost, with removal plan for low-alpha features starting with watchlist
status: planned
created: 2026-03-06T22:00:00Z
---

# PRD: Feature Alpha Audit

## Executive Summary

A comprehensive audit of all 24 discrete features in Options Arena, scoring each on a
4-dimension alpha framework: user value, analytical quality, maintenance cost, and coupling
risk. The audit identifies dead database artifacts for cleanup, 4 features for simplification,
and confirms watchlist removal as the highest-ROI cut (78 tests, ~1,000 lines, zero analytical
value). The codebase is lean overall — no feature is grossly wasteful, but targeted pruning
reduces test surface by ~170 tests and ~1,400 lines.

## Problem Statement

### What problem are we solving?

Options Arena has grown to 102 source files, ~29,390 lines of Python, and 3,854 tests across
24 features. Each feature carries ongoing maintenance cost: test execution time, dependency
management, cognitive load for contributors, and coupling surface for regressions. Some
features were built speculatively and may deliver insufficient value relative to their cost.

Without periodic pruning, the codebase accumulates dead code, over-tested optional features,
and organizational features that don't improve analytical output. This audit quantifies each
feature's return on maintenance investment and identifies safe removal/simplification targets.

### Why is this important now?

- Test suite runtime grows with test count — removing 170 tests improves CI feedback time
- The watchlist feature (78 tests, full CRUD, dedicated frontend page) provides zero
  analytical value and is confirmed unused
- Dead database artifacts (`intelligence_snapshots` ghost table, `thematic_tags_json` dead
  column) waste schema space and confuse future contributors
- OpenBB enrichment carries 110 tests for a config-gated optional feature — disproportionate

## Audit Methodology

### Alpha Score Formula

```
Alpha = (User Value + Analytical Quality) - (Maintenance Cost + Coupling Risk)
```

Each dimension scored 1-5:
- **User Value**: 5 = core workflow, 3 = occasional, 1 = never observed in use
- **Analytical Quality**: 5 = directly improves verdict accuracy, 3 = context, 1 = none
- **Maintenance Cost**: 5 = many files/deps/breakage, 3 = moderate, 1 = trivial
- **Coupling Risk**: 5 = deeply woven, 3 = moderate, 1 = isolated

### Tier Classification

- **Keep** (alpha >= 2 or essential infrastructure)
- **Simplify** (alpha 0-1, valuable but over-scoped)
- **Remove** (confirmed unused or alpha < 0 with low coupling)
- **Investigate** (need usage data to decide)

## Feature Assessment

### Complete Scoring Table

| # | Feature | User | Analytical | Maint | Coupling | Alpha | Tier |
|---|---------|------|------------|-------|----------|-------|------|
| 1 | Core scan pipeline | 5 | 5 | 4 | 5 | 1 | Keep (baseline) |
| 2 | AI debate (8 agents) | 5 | 5 | 4 | 4 | 2 | Keep (baseline) |
| 3 | Batch debate | 4 | 4 | 2 | 3 | 3 | Keep |
| 4 | Debate export | 2 | 1 | 2 | 1 | 0 | Simplify |
| 5 | **Watchlist** | **3** | **1** | **3** | **2** | **-1** | **Remove** |
| 6 | Outcome tracking + Analytics | 3 | 4 | 4 | 3 | 0 | Simplify |
| 7 | Score history & trending | 3 | 3 | 2 | 1 | 3 | Keep |
| 8 | Scan delta | 2 | 2 | 1 | 1 | 2 | Keep |
| 9 | Sector filtering | 4 | 3 | 2 | 3 | 2 | Keep |
| 10 | Earnings calendar | 4 | 4 | 2 | 4 | 2 | Keep |
| 11 | ChainProvider (CBOE+yfinance) | 3 | 4 | 3 | 2 | 2 | Keep |
| 12 | OpenBB enrichment | 2 | 3 | 3 | 2 | 0 | Simplify |
| 13 | Intelligence service | 2 | 3 | 3 | 3 | -1 | Investigate |
| 14 | Metadata index | 3 | 2 | 3 | 4 | -2 | Investigate |
| 15 | Health check | 3 | 1 | 2 | 2 | 0 | Keep |
| 16 | Universe management | 4 | 3 | 3 | 5 | -1 | Keep (essential) |
| 17 | FRED integration | 2 | 4 | 1 | 2 | 3 | Keep |
| 18 | CLI rich output | 4 | 1 | 2 | 3 | 0 | Keep (essential) |
| 19 | WebSocket progress | 4 | 1 | 2 | 3 | 0 | Keep (essential) |
| 20 | Vue SPA | 5 | 1 | 4 | 4 | -2 | Keep (essential) |
| 21 | Pre-scan filters | 4 | 3 | 2 | 3 | 2 | Keep |
| 22 | Dimensional scores | 3 | 4 | 2 | 3 | 2 | Keep |
| 23 | Market regime | 3 | 4 | 2 | 3 | 2 | Keep |
| 24 | Dead DB artifacts | 0 | 0 | 1 | 1 | -2 | Remove |

### Summary by Tier

- **Keep**: 16 features (core value or essential infrastructure)
- **Simplify**: 4 features (~800 lines reducible, ~80 tests reducible)
- **Remove**: 2 items (watchlist + dead DB artifacts — 78+ tests, ~1,000+ lines)
- **Investigate**: 2 features (need usage/quality data)

## Requirements

### FR-1: Remove Watchlist Feature (Priority 1 — This Epic)

Remove all watchlist code, tests, frontend, and API surface. DB tables become orphaned
(harmless — no migration needed).

**Files to delete:**
- `src/options_arena/cli/watchlist.py`
- `src/options_arena/api/routes/watchlist.py`
- `src/options_arena/models/watchlist.py`
- `web/src/pages/WatchlistPage.vue`
- `web/src/stores/watchlist.ts`
- `tests/unit/cli/test_watchlist_cli.py`
- `tests/unit/api/test_watchlist_routes.py`
- `tests/unit/data/test_repository_watchlist.py`
- `tests/unit/models/test_watchlist.py`
- `web/e2e/suites/watchlist/watchlist.spec.ts`

**Files to modify:**
- `src/options_arena/models/__init__.py` — remove watchlist re-exports
- `src/options_arena/data/repository.py` — remove 8 watchlist methods
- `src/options_arena/api/app.py` — remove watchlist router include
- `src/options_arena/cli/app.py` — remove watchlist subcommand registration
- `web/src/router/index.ts` — remove `/watchlist` route
- `web/src/components/TickerDrawer.vue` — remove "Add to Watchlist" button
- `web/src/pages/DashboardPage.vue` — remove watchlist references (if any)
- `web/src/pages/ScanResultsPage.vue` — remove watchlist import/usage (if any)

**Blast radius**: 78 tests removed, ~1,000 lines removed. No DB migration.
**Rollback**: `git revert` the removal commit(s).

### FR-2: Remove Dead DB Artifacts (Priority 2)

**2a. Drop `intelligence_snapshots` ghost table:**
- New migration file: `DROP TABLE IF EXISTS intelligence_snapshots;`
- Zero Python code references this table (confirmed by grep)

**2b. Drop `ticker_scores.thematic_tags_json` dead column:**
- New migration file: `ALTER TABLE ticker_scores DROP COLUMN thematic_tags_json;`
- Zero Python code references `thematic_tags` (confirmed by grep)
- Requires SQLite 3.35.0+ (Python 3.13 ships 3.45+)

### FR-3: Simplify Debate Export (Priority 3 — Future)

- Remove PDF export path (weasyprint optional dependency)
- Keep markdown export only
- Remove 501 "weasyprint not installed" error handling
- Update CLI `--export` to only accept `md`
- ~150 lines, ~10 tests removed

### FR-4: Reduce OpenBB Test Surface (Priority 4 — Future)

- Audit 110 OpenBB-related tests for redundancy
- Consolidate config-gating tests (many test identical patterns)
- Target: reduce from 110 to ~40 tests
- ~70 tests removed, zero production code changes

### FR-5: Investigate Intelligence Service (Priority 5 — Future)

- Compare debate quality with/without intelligence data
- If no measurable improvement: remove `IntelligencePackage` from `run_debate()` signature
- If valuable: reduce test count for config-gating patterns
- Decision deferred pending A/B data

### FR-6: Investigate Metadata Index Simplification (Priority 6 — Future)

- Consider removing `universe index` CLI bulk command
- Keep pipeline Phase 1/Phase 3 incremental updates
- Remove `/api/universe/index` endpoint
- Decision deferred pending Russell 2000 usage data

## Non-Functional Requirements

### NFR-1: Test Suite Reduction
- FR-1 removes 78 tests (unit + E2E)
- FR-2 removes 0 tests (dead DB only)
- FR-3 removes ~10 tests
- FR-4 removes ~70 tests
- Total potential: ~158 tests removed

### NFR-2: Architecture Boundary Preservation
All removals must preserve the boundary table from CLAUDE.md. No removal may:
- Make `models/` depend on I/O or APIs
- Make `scoring/` import from `services/`
- Make `scan/` call `pricing/` directly

### NFR-3: No Breaking Changes to Core Pipeline
The scan pipeline and debate orchestrator must remain fully functional after all removals.
Verify via `uv run pytest tests/unit/scan/ tests/unit/agents/ -v`.

## Success Criteria

| Metric | Target |
|--------|--------|
| Watchlist completely removed | All files deleted, no import errors |
| Dead DB artifacts cleaned | Ghost table + dead column dropped |
| All tests pass after removal | `uv run pytest tests/ -v` green |
| Type checking passes | `uv run mypy src/ --strict` green |
| Lint passes | `uv run ruff check .` green |
| Frontend builds | `cd web && npm run build` succeeds |
| No runtime errors on core flows | Scan + debate work without watchlist |

## Implementation Order

1. **Watchlist removal** (FR-1) — largest ROI, lowest risk, independent
2. **Dead DB artifacts** (FR-2) — trivial, independent
3. **Debate export simplification** (FR-3) — independent, low risk
4. **OpenBB test reduction** (FR-4) — test-only changes
5. **Intelligence investigation** (FR-5) — requires data collection
6. **Metadata investigation** (FR-6) — requires usage analysis
