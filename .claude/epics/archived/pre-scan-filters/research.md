# Research: pre-scan-filters

## PRD Summary

Replace 15+ filter fields scattered across `ScanConfig`, `PricingConfig`, phase modules, and the pipeline orchestrator with a unified `ScanFilterSpec` composed of three typed stage models (`UniverseFilters`, `ScoringFilters`, `OptionsFilters`). Each stage enforces correct filter ordering at the type level, eliminating wasted API calls by moving cheap filters earlier. New `--min-score` and `--min-confidence` pre-scan cutoffs. Target: S&P 500 scans under 8 minutes.

## Relevant Existing Modules

- `models/config.py` — Defines `ScanConfig` (15+ filter fields) and `PricingConfig` (9 contract selection fields). The primary refactoring target.
- `models/enums.py` — All required enums exist: `ScanPreset`, `GICSSector`, `GICSIndustryGroup` (26 groups + 130 aliases), `MarketCapTier`, `SignalDirection`.
- `scan/pipeline.py` — Orchestrator (352 lines). Applies `direction_filter` post-Phase 2. Will gain `ScoringFilters` cutoff logic.
- `scan/phase_universe.py` — Phase 1. Currently receives `scan_config: ScanConfig`. Uses `sectors`, `industry_groups`, `custom_tickers`, `ohlcv_min_bars`. Will receive `UniverseFilters` and add market_cap_tiers pre-OHLCV filter.
- `scan/phase_scoring.py` — Phase 2. Uses `adx_trend_threshold`, `rsi_overbought`, `rsi_oversold` (NOT filter fields — stay on ScanConfig).
- `scan/phase_options.py` — Phase 3. Uses `min_price`, `max_price`, `min_dollar_volume`, `top_n`, `exclude_near_earnings_days`, `min_iv_rank`, `market_cap_tiers`, plus all PricingConfig contract filters. Will receive `OptionsFilters`.
- `scan/phase_persist.py` — Phase 4. Does NOT use config. No changes needed.
- `cli/commands.py` — CLI `scan` command. Builds `scan_overrides` dict from args, creates configs. Already has `--min-score`.
- `api/schemas.py` — `ScanRequest` model. Already has `min_score`, all filter fields.
- `api/routes/scan.py` — Builds overrides from `ScanRequest`, passes to pipeline. Also has post-scan query filters.
- `data/_metadata.py` — `MetadataMixin` with `get_all_ticker_metadata()` — returns `TickerMetadata` with `market_cap_tier` field. Used in Phase 1 for sector enrichment.

## Existing Patterns to Reuse

### Immutable Config Override Pattern
CLI and API both use: `scan_overrides: dict[str, object] = {}` → apply to defaults. Must preserve this for `ScanFilterSpec` construction from flat CLI args.

### Phase Function Signature Pattern
Each phase receives explicit typed params (`scan_config: ScanConfig`, `pricing_config: PricingConfig`). Must replace with `UniverseFilters`/`OptionsFilters` — NOT pass full `ScanFilterSpec` to phases.

### Ticker Metadata Enrichment (Phase 1)
`phase_universe.py` already calls `repository.get_all_ticker_metadata()` to enrich sector/industry_group maps. Market cap filtering can piggyback on this existing metadata load — no new API call.

### Liquidity Pre-Filter Pattern (Phase 3)
`phase_options.py` lines 203-233 apply `min_dollar_volume`, `min_price`, `max_price` BEFORE chain fetch. Must preserve this ordering and extend with market_cap and earnings checks.

### NaN/Inf Defense
All numeric validators use `math.isfinite()` guard. New filter models must follow same pattern.

### Post-Scan Query Filters (Out of Scope)
API routes have `min_score`, `min_confidence` as query params for post-scan result filtering. These are SEPARATE from pre-scan pipeline filters and should remain untouched.

## Existing Code to Extend

### `models/config.py` — Remove filter fields from ScanConfig/PricingConfig
**ScanConfig filter fields to move (13 fields):**
- `top_n`, `min_score`, `min_price`, `max_price`, `min_dollar_volume` → OptionsFilters/ScoringFilters
- `ohlcv_min_bars` → UniverseFilters
- `sectors`, `industry_groups`, `market_cap_tiers`, `custom_tickers` → UniverseFilters
- `exclude_near_earnings_days`, `direction_filter`, `min_iv_rank` → OptionsFilters/ScoringFilters
- `min_dte`, `max_dte` → OptionsFilters

**ScanConfig fields to KEEP (non-filter):**
- `adx_trend_threshold`, `rsi_overbought`, `rsi_oversold` — scoring thresholds
- `options_per_ticker_timeout`, `options_concurrency` — rate limiting
- `enable_iv_analytics`, `enable_flow_analytics`, `enable_fundamental`, `enable_regime` — feature toggles

**ScanConfig field to REMOVE:** `options_batch_size` (confirmed unused — zero references outside config.py)

**PricingConfig fields to move to OptionsFilters (9 fields):**
- `dte_min`, `dte_max`, `min_oi`, `min_volume`, `max_spread_pct` — contract selection
- `delta_primary_min`, `delta_primary_max`, `delta_fallback_min`, `delta_fallback_max` — delta targeting

**PricingConfig fields to KEEP:**
- `risk_free_rate_fallback`, `iv_solver_tol`, `iv_solver_max_iter`, `delta_target` — pricing math

**DTE duplication:** `ScanConfig.min_dte/max_dte` duplicate `PricingConfig.dte_min/dte_max`. Consolidate into `OptionsFilters` only.

### `scan/pipeline.py` — Add ScoringFilters cutoff between Phase 2 and Phase 3
Currently applies `direction_filter` at line ~147-158. Add `min_score` and `min_direction_confidence` cutoffs alongside.

### `scan/phase_universe.py` — Add market_cap_tiers filter before OHLCV fetch
Already loads all metadata at line ~109-119 for sector enrichment. Add market_cap tier filtering using same data — zero additional API calls.

### `scan/phase_options.py` — Move earnings check before chain fetch
Currently checks `exclude_near_earnings_days` at line ~461-469 AFTER chain fetch. Move before chain fetch to save API calls per dropped ticker.

### `cli/commands.py` — Build ScanFilterSpec from CLI args
Currently builds `scan_overrides` and `pricing_overrides` dicts. Must build `ScanFilterSpec` instead. `--min-score` already exists; add `--min-confidence`.

### `api/schemas.py` — ScanRequest builds ScanFilterSpec
Already has all fields. Add `min_direction_confidence` field. Internal `to_filter_spec()` method to construct `ScanFilterSpec`.

## Potential Conflicts

### Config Migration — HIGH IMPACT
Removing 13+ fields from `ScanConfig` and 9 from `PricingConfig` affects every test that constructs these models. ~200+ test files may need updating. **Mitigation:** Provide backward-compatible factory or keep deprecated fields as aliases during migration.

### Phase Function Signature Changes — MEDIUM IMPACT
Changing `scan_config: ScanConfig` → `universe_filters: UniverseFilters` in phase functions breaks all callers and tests. **Mitigation:** Change signatures atomically with callers. Consider phased approach: add `ScanFilterSpec` first, migrate phases one at a time.

### PricingConfig Consumer Sites — MEDIUM IMPACT
`scoring/contracts.py` reads `PricingConfig.dte_min`, `delta_primary_min`, etc. These call sites must read from `OptionsFilters` instead. **Mitigation:** Pass `OptionsFilters` alongside `PricingConfig` (keep pricing math fields separate from contract filters).

### Frontend PreScanFilters.vue — OUT OF SCOPE
Vue frontend already emits `PreScanFilterPayload`. Backend changes transparent if API contract stays the same.

## Open Questions

1. **Filter persistence:** PRD mentions "filter spec is serializable." Should we add a `filter_spec_json TEXT` column to `scan_runs`? (Would be migration 031.) This enables reproducibility but is not strictly required for filter functionality.

2. **ScanConfig backward compatibility:** Should we keep deprecated field aliases on `ScanConfig` (forwarding to `filters.universe.*` etc.) for a transition period, or do a clean break? Clean break is simpler but requires updating ~200 tests in one shot.

3. **PricingConfig split:** Should `delta_target` move to `OptionsFilters` since it's used in contract selection, or stay in `PricingConfig` since it's also used in pricing math? PRD puts it in PricingConfig.

4. **Preset field:** PRD places `preset` in `UniverseFilters`. Currently `preset` is a parameter to `run()` on the pipeline, NOT on `ScanConfig`. Should it move into the filter spec or remain a top-level param?

5. **Phase 2 thresholds:** `adx_trend_threshold`, `rsi_overbought`, `rsi_oversold` are scoring parameters, not filters. PRD keeps them on `ScanConfig`. Confirm this is correct (they influence direction classification, not filtering).

## Recommended Architecture

### Layer 1: New Filter Models (`models/filters.py`)
Create `UniverseFilters`, `ScoringFilters`, `OptionsFilters`, `ScanFilterSpec` as frozen Pydantic models with full validators (isfinite, range checks, cross-field constraints).

### Layer 2: Config Migration (`models/config.py`)
Add `filters: ScanFilterSpec = ScanFilterSpec()` to `ScanConfig`. Keep non-filter fields. Remove `options_batch_size`. Approach for DTE/delta duplication: single source in `OptionsFilters`, remove from `PricingConfig`.

### Layer 3: Pipeline Integration (`scan/pipeline.py`)
Orchestrator extracts `filter_spec` from config, passes stage-specific slices to phases. Adds `ScoringFilters` cutoff between Phase 2 and Phase 3 (alongside existing `direction_filter`).

### Layer 4: Phase Updates (`scan/phase_*.py`)
Phase 1 receives `UniverseFilters`, applies market_cap before OHLCV. Phase 3 receives `OptionsFilters`, reorders earnings before chain fetch. Phase 2 and Phase 4 unchanged.

### Layer 5: Entry Points (`cli/commands.py`, `api/routes/scan.py`)
CLI builds `ScanFilterSpec` from flat args. API builds from `ScanRequest` body. Both pass through to pipeline.

### Implementation Order
1. **Foundation:** `models/filters.py` + tests (no existing code changes)
2. **Config migration:** Move fields from ScanConfig/PricingConfig → ScanFilterSpec
3. **Pipeline integration:** Orchestrator + Phase 1 + Phase 3 updates
4. **Entry points:** CLI + API mapping
5. **Cleanup:** Remove dead fields, update remaining tests

## Test Strategy Preview

### Existing Test Patterns
- **Model validation tests:** `tests/unit/models/test_config_prescan.py` (137 lines) — NaN rejection, cross-field validation, enum normalization. Follow same patterns.
- **API schema tests:** `tests/unit/api/test_schemas_prescan.py` (170 lines) — ScanRequest validation.
- **Phase tests:** `tests/unit/scan/test_phase_universe.py`, `test_phase_options.py` — mock services, verify filtering logic.
- **Pipeline integration:** `tests/unit/scan/test_pipeline_prescan_filters.py` — `TestCombinedPreScanFilters` class.
- **Mocking:** Pure model validation (no mocks). Phase tests mock services via `AsyncMock`.

### New Tests Needed (~40-50)
- `tests/unit/models/test_filters.py` — All validators, edge cases, cross-field constraints
- `tests/unit/scan/test_phase_universe_filters.py` — Market cap filter with metadata
- `tests/unit/scan/test_scoring_filters.py` — min_score/min_confidence cutoffs in orchestrator
- `tests/unit/scan/test_phase_options_filters.py` — Earnings pre-filter, reordered operations
- `tests/unit/scan/test_filter_integration.py` — End-to-end ScanFilterSpec flow
- `tests/unit/cli/test_scan_filter_args.py` — CLI arg → ScanFilterSpec mapping
- `tests/unit/api/test_scan_filter_request.py` — ScanRequest → ScanFilterSpec mapping

### Migration Number
Next available: `031` (latest is `030_backfill_prediction_contracts.sql`)

## Estimated Complexity

**L (Large)** — Justification:
- 7+ files modified, 1 new file created
- Config migration affects ~200 test files constructing ScanConfig/PricingConfig
- Phase function signature changes across 3 phase modules + orchestrator
- CLI and API entry point updates
- ~40-50 new tests
- Cross-field validator complexity (delta ranges, DTE ranges)
- Careful backward compatibility considerations

Estimated: 8-10 issues in the epic, ~3-4 implementation waves.
