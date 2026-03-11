---
name: pre-scan-filters
status: backlog
created: 2026-03-11T13:34:18Z
progress: 0%
prd: .claude/prds/pre-scan-filters.md
github: https://github.com/jobu711/options_arena/issues/464
---

# Epic: pre-scan-filters

## Overview

Consolidate 22+ filter fields scattered across `ScanConfig` (13 fields) and `PricingConfig` (9 contract selection fields) into a unified `ScanFilterSpec` composed of three typed stage models: `UniverseFilters` (Phase 1), `ScoringFilters` (post-Phase 2), `OptionsFilters` (Phase 3). Clean break — no deprecated aliases. Add `min_score` and `min_direction_confidence` as pre-scan cutoffs. Persist filter spec with scan results (migration 031). Move cheap filters earlier to reduce wasted API calls.

## Architecture Decisions

1. **Clean break, no backward compat**: Filter fields removed from `ScanConfig`/`PricingConfig` outright. All ~200 tests updated in one pass. Simpler codebase, no legacy forwarding code.

2. **`preset` moves into `UniverseFilters`**: Currently a param on `pipeline.run()`. Becomes a filter field so `ScanFilterSpec` is the complete filter description. Pipeline `run()` loses `preset` param, reads from `filter_spec.universe.preset`.

3. **`delta_target` moves to `OptionsFilters`**: Used exclusively in contract selection (`scoring/contracts.py`), not BSM/BAW pricing math. Lives alongside the other delta fields.

4. **Scoring thresholds stay on `ScanConfig`**: `adx_trend_threshold`, `rsi_overbought`, `rsi_oversold` influence direction classification, not filtering. Remain as non-filter config.

5. **Phase functions receive stage-specific filter models**: `phase_universe.py` gets `UniverseFilters`, `phase_options.py` gets `OptionsFilters`. NOT the full `ScanFilterSpec`. Preserves explicit parameter pattern.

6. **`ScanConfig.filters: ScanFilterSpec`**: Config holds the filter spec. CLI/API build overrides dict → construct `ScanFilterSpec` → inject into `ScanConfig`. Env vars work via `ARENA_SCAN__FILTERS__UNIVERSE__TOP_N=30`.

7. **Filter persistence**: Add `filter_spec_json TEXT` column to `scan_runs` (migration 031). Stores `ScanFilterSpec.model_dump_json()` for reproducibility.

## Technical Approach

### Models (`models/filters.py`)
New frozen Pydantic models with full validators:
- `UniverseFilters`: preset, sectors, industry_groups, custom_tickers, market_cap_tiers, ohlcv_min_bars, min_price, max_price
- `ScoringFilters`: direction_filter, min_score, min_direction_confidence
- `OptionsFilters`: top_n, min_dollar_volume, min_dte, max_dte, exclude_near_earnings_days, min_iv_rank, min_oi, min_volume, max_spread_pct, delta_primary_min/max, delta_fallback_min/max, delta_target
- `ScanFilterSpec`: universe + scoring + options composition

All validators: `isfinite()`, range checks, cross-field (min_dte ≤ max_dte, delta primary ⊂ fallback), custom_tickers normalization (uppercase, max 200).

### Config Migration (`models/config.py`)
- `ScanConfig` loses 13 filter fields + `options_batch_size`. Gains `filters: ScanFilterSpec = ScanFilterSpec()`.
- `PricingConfig` loses 9 contract selection fields (dte, delta, OI, volume, spread). Keeps `risk_free_rate_fallback`, `iv_solver_tol`, `iv_solver_max_iter`.
- `AppSettings` unchanged (nested delimiter still works).

### Pipeline + Phases (`scan/`)
- `pipeline.run()` loses `preset` param. Reads from `self._settings.scan.filters`.
- Orchestrator applies `ScoringFilters` (direction + min_score + min_confidence) between Phase 2 and Phase 3.
- Phase 1 receives `UniverseFilters`, applies market_cap_tiers pre-OHLCV using cached `ticker_metadata`.
- Phase 3 receives `OptionsFilters`, reorders earnings check before chain fetch.
- Phase 2 and Phase 4 unchanged (Phase 2 uses `ScanConfig` for scoring thresholds only).

### Entry Points (`cli/`, `api/`)
- CLI builds `ScanFilterSpec` from flat `--min-score`, `--sector`, `--min-dte`, etc. args. Adds `--min-confidence`.
- API `ScanRequest` gains `min_direction_confidence` field. Builds `ScanFilterSpec` internally.

### Persistence (`data/`)
- Migration 031: `ALTER TABLE scan_runs ADD COLUMN filter_spec_json TEXT`.
- Phase 4 stores `filter_spec.model_dump_json()`.

## Implementation Strategy

**Wave 1** (foundation — non-breaking):
- Issue #465: Create filter models + tests

**Wave 2** (big migration — atomic):
- Issue #466: Config migration + pipeline + phases + CLI + API + test fixup

**Wave 3** (new features — parallelizable):
- Issue #467: Scoring cutoffs (min_score, min_confidence)
- Issue #468: Phase optimizations (market cap pre-filter, earnings reorder)

**Wave 4** (persistence):
- Issue #469: Migration 031 + filter spec storage

**Wave 5** (verification):
- Issue #470: Integration tests + final cleanup

## Task Breakdown Preview

- [ ] **#465 Create filter models** — `models/filters.py` with `UniverseFilters`, `ScoringFilters`, `OptionsFilters`, `ScanFilterSpec`. All validators + unit tests. Re-export from `__init__.py`. ~40 tests.
- [ ] **#466 Config migration + consumer updates** — Remove filter fields from `ScanConfig`/`PricingConfig`. Add `filters: ScanFilterSpec`. Update pipeline `run()` signature (drop `preset`). Update all 4 phase function signatures. Update CLI arg → config mapping. Update API `ScanRequest` → config mapping. Fix all broken tests (~200 files).
- [ ] **#467 Scoring cutoffs** — Apply `min_score` and `min_direction_confidence` cutoffs in pipeline orchestrator post-Phase 2 (alongside existing direction filter). ~10 tests.
- [ ] **#468 Phase optimizations** — Phase 1: market_cap_tiers filter using cached `ticker_metadata` before OHLCV fetch. Phase 3: move earnings check before chain fetch. ~15 tests.
- [ ] **#469 Filter persistence** — Migration 031 (`filter_spec_json TEXT` on `scan_runs`). Phase 4 stores spec. Repository read-back for reproducibility. ~8 tests.
- [ ] **#470 Integration tests + cleanup** — End-to-end `ScanFilterSpec` flow through all phases. Verify default spec produces identical behavior. Remove any dead code. ~10 tests.

## Dependencies

- **Internal**: `ticker_metadata` SQLite table must be populated for Phase 1 market cap filtering (from metadata-index epic — already complete)
- **Internal**: Pipeline phase decomposition (already complete) — provides clean phase boundaries
- **No external dependencies** — all filter logic is pure Python + Pydantic

## Success Criteria (Technical)

- `ScanFilterSpec` is the sole source of truth for all pre-scan filters
- Zero filter fields remain on `ScanConfig` or `PricingConfig`
- `options_batch_size` removed from `ScanConfig`
- Default `ScanFilterSpec()` produces identical scan behavior to current defaults
- `min_score` cutoff demonstrably reduces Phase 3 ticker count (logged)
- Market cap filtering in Phase 1 (before OHLCV fetch, no API call)
- Earnings check before chain fetch in Phase 3
- Filter spec persisted with scan results (migration 031)
- All existing tests pass, ~80 new tests added
- Full test suite green: `uv run pytest tests/ -n auto`
- Type check clean: `uv run mypy src/ --strict`
- Lint clean: `uv run ruff check .`

## Estimated Effort

**L (Large)** — 6 issues across 5 waves. The config migration (Issue #2) is the critical path and largest single task due to ~200 test files needing updates. Issues #3-#5 are smaller and can partially parallelize after the migration lands.

## Tasks Created
- [ ] #465 - Create filter models (parallel: false)
- [ ] #466 - Config migration and consumer updates (parallel: false)
- [ ] #467 - Scoring cutoffs in pipeline orchestrator (parallel: true)
- [ ] #468 - Phase optimizations (market cap pre-filter, earnings reorder) (parallel: true)
- [ ] #469 - Filter persistence (migration 031) (parallel: true)
- [ ] #470 - Integration tests and cleanup (parallel: false)

Total tasks: 6
Parallel tasks: 3 (#467, #468, #469 can run concurrently after #466)
Sequential tasks: 3 (#465 → #466 → ... → #470)
Estimated total effort: 29-41 hours

## Test Coverage Plan
Total test files planned: 7
Total test cases planned: ~83
