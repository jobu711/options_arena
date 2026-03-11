---
name: pre-scan-filters
description: Unified staged filter model replacing scattered scan filter fields across ScanConfig/PricingConfig with optimized phase ordering
status: planned
created: 2026-03-11T13:09:33Z
---

# PRD: pre-scan-filters

## Executive Summary

Replace the 15+ filter mechanisms scattered across `ScanConfig`, `PricingConfig`, phase modules, and the pipeline orchestrator with a unified `ScanFilterSpec` composed of three typed stage models (`UniverseFilters`, `ScoringFilters`, `OptionsFilters`). Each stage enforces correct filter ordering at the type level, eliminating wasted API calls by moving cheap filters earlier (market cap before OHLCV, min_score before chain fetch, earnings before chain fetch). Target: scans complete in under 8 minutes.

## Problem Statement

### What problem are we solving?

The scan pipeline's filter logic is fragmented:

1. **Filter fields are scattered** across `ScanConfig` (sectors, direction, min_price, market_cap_tiers, min_iv_rank, exclude_near_earnings_days), `PricingConfig` (dte_min/max, min_oi, min_volume, max_spread_pct, delta ranges), and hardcoded phase logic. There is no single model that describes "what this scan will filter."

2. **Expensive filters applied too late** — market cap tier filtering happens in Phase 3 *after* fetching option chains. Earnings proximity is checked *after* chain fetch. There is no composite score cutoff before Phase 3, so low-scoring tickers still consume expensive chain-fetch slots.

3. **Duplicated config fields** — `min_dte`/`max_dte` exist on both `ScanConfig` and `PricingConfig`. `options_batch_size` on `ScanConfig` is unused.

4. **No pre-scan score gate** — `min_score` only exists as a post-scan API query param. Tickers scoring 5/100 still go through full Phase 3 processing.

### Why is this important now?

With ~4,400 tests, 29 completed epics, and a stable 4-phase pipeline architecture, the scan system is mature enough for a filter redesign without risk of destabilizing active work. The pipeline decomposition (epic: pipeline-phase-extraction) and service layer unification (epic: service-layer-unification) provide clean phase boundaries to hook filters into.

## User Stories

### US-1: Unified filter configuration
**As a** developer maintaining the scan pipeline,
**I want** all pre-scan filter criteria defined in a single `ScanFilterSpec` model,
**So that** I can understand, serialize, and test the complete filter configuration without hunting across multiple config classes.

**Acceptance criteria:**
- `ScanFilterSpec` is the sole source of truth for all pre-scan filters
- Old `ScanConfig`/`PricingConfig` filter fields are removed or deprecated
- Filter spec is persisted with scan results for reproducibility

### US-2: Faster scans via optimized filter ordering
**As a** user running scans,
**I want** cheap filters (market cap, min_score, earnings proximity) applied before expensive operations (OHLCV fetch, chain fetch),
**So that** scans complete in under 8 minutes.

**Acceptance criteria:**
- Market cap filter uses cached `ticker_metadata` in Phase 1 (no API call)
- `min_score` cutoff drops low-scoring tickers before Phase 3
- Earnings proximity check runs before chain fetch
- Benchmark shows measurable reduction in Phase 3 ticker count

### US-3: New pre-scan filter capabilities
**As a** user configuring scans,
**I want** `min_score` and `min_direction_confidence` as pre-scan filters,
**So that** I can focus Phase 3 processing on high-conviction tickers only.

**Acceptance criteria:**
- `--min-score 40` CLI flag drops tickers below 40 composite score after Phase 2
- `--min-confidence 0.5` CLI flag drops tickers with direction confidence below 0.5
- Both available via API `ScanRequest` body

## Architecture & Design

### Chosen Approach

**Staged Filter Pipeline (Approach B)** — Three filter stage models mapped to pipeline phases, composed into a single `ScanFilterSpec`. The stage structure enforces correct filter ordering at the type level.

Rationale: Naturally maps to the existing 4-phase scan architecture, prevents accidental misplacement of expensive filters, and makes the min_score optimization a first-class concern.

### Module Changes

**New file:**
- `src/options_arena/models/filters.py` — `UniverseFilters`, `ScoringFilters`, `OptionsFilters`, `ScanFilterSpec`

**Modified files:**
- `src/options_arena/models/config.py` — `ScanConfig` loses filter fields (replaced by `filters: ScanFilterSpec`), `PricingConfig` loses duplicated fields. Remove unused `options_batch_size`.
- `src/options_arena/models/__init__.py` — re-export new filter models
- `src/options_arena/scan/pipeline.py` — orchestrator passes `ScanFilterSpec` to phases, applies `ScoringFilters` cutoffs post-Phase 2
- `src/options_arena/scan/phase_universe.py` — receives `UniverseFilters` instead of scattered config fields
- `src/options_arena/scan/phase_options.py` — receives `OptionsFilters`, reordered: market cap + earnings before chain fetch
- `src/options_arena/cli/scan.py` — CLI args map to `ScanFilterSpec`
- `src/options_arena/api/routes/scan.py` — `ScanRequest` builds `ScanFilterSpec` from request body

**Boundary compliance:** `models/` defines shapes only (no logic). Filter *application* stays in `scan/` phases. No boundary violations.

### Data Models

```python
# models/filters.py

class UniverseFilters(BaseModel):
    """Phase 1 — cheap filters applied before/during OHLCV fetch."""
    model_config = ConfigDict(frozen=True)

    preset: ScanPreset = ScanPreset.SP500
    sectors: list[GICSSector] = []
    industry_groups: list[GICSIndustryGroup] = []
    custom_tickers: list[str] = []
    ohlcv_min_bars: int = 200
    min_price: float = 10.0
    max_price: float | None = None
    market_cap_tiers: list[MarketCapTier] = []

class ScoringFilters(BaseModel):
    """Post-Phase 2 — applied after indicators + composite scoring."""
    model_config = ConfigDict(frozen=True)

    direction_filter: SignalDirection | None = None
    min_score: float = 0.0
    min_direction_confidence: float = 0.0

class OptionsFilters(BaseModel):
    """Phase 3 — applied during options chain processing."""
    model_config = ConfigDict(frozen=True)

    top_n: int = 50
    min_dollar_volume: float = 10_000_000.0
    min_dte: int = 30
    max_dte: int = 365
    exclude_near_earnings_days: int | None = None
    min_iv_rank: float | None = None
    min_oi: int = 100
    min_volume: int = 1
    max_spread_pct: float = 30.0
    delta_primary_min: float = 0.20
    delta_primary_max: float = 0.50
    delta_fallback_min: float = 0.10
    delta_fallback_max: float = 0.80

class ScanFilterSpec(BaseModel):
    """Composite — single object describing all pre-scan filters."""
    model_config = ConfigDict(frozen=True)

    universe: UniverseFilters = UniverseFilters()
    scoring: ScoringFilters = ScoringFilters()
    options: OptionsFilters = OptionsFilters()
```

**Validators:**
- `min_price` / `max_price`: `isfinite()` + `> 0`
- `min_score`: `0.0 <= v <= 100.0` + `isfinite()`
- `min_direction_confidence`: `0.0 <= v <= 1.0`
- `top_n`: `> 0`
- `min_dte` / `max_dte`: model_validator ensures `min_dte <= max_dte`
- `delta_*`: model_validator ensures primary range is subset of fallback range
- `custom_tickers`: max length 200, uppercase normalization

### Core Logic

**Optimized filter ordering:**

```
Phase 1 (UniverseFilters):
  1. Fetch optionable universe
  2. Apply preset filter
  3. Apply sector / industry_group filter
  4. Apply custom_tickers override
  5. Apply market_cap_tiers filter (from cached ticker_metadata — no API call)
  6. Apply min_price / max_price filter (from cached metadata)
  7. Batch fetch OHLCV
  8. Apply ohlcv_min_bars filter

Post-Phase 2 (ScoringFilters) — in pipeline.py orchestrator:
  1. Apply direction_filter (existing)
  2. Apply min_score cutoff (NEW)
  3. Apply min_direction_confidence cutoff (NEW)

Phase 3 (OptionsFilters):
  1. Apply min_dollar_volume liquidity pre-filter (existing)
  2. Apply top_n selection (existing)
  3. Fetch earnings date BEFORE chain fetch
  4. Apply exclude_near_earnings_days BEFORE chain fetch
  5. Fetch option chains + ticker info concurrently
  6. Apply min_iv_rank (requires chain data — stays post-chain)
  7. Contract selection using delta/DTE/OI/volume/spread filters
```

**Key optimizations:**
- Market cap filter in Phase 1 uses cached `ticker_metadata` table — no API call, drops tickers before OHLCV fetch
- `min_score` cutoff post-Phase 2 prevents low-scoring tickers from entering Phase 3
- Earnings check moved before chain fetch saves one API call per dropped ticker
- Removal of `options_batch_size` dead field

**Config migration:** `ScanConfig` retains non-filter fields (`options_concurrency`, `ohlcv_batch_size`, `source`). Filter fields replaced by `filters: ScanFilterSpec`. `PricingConfig` loses `dte_min`, `dte_max`, `min_oi`, `min_volume`, `max_spread_pct`, `delta_*` — read from `ScanFilterSpec.options` at call sites.

## Requirements

### Functional Requirements

1. `ScanFilterSpec` is the single source of truth for all pre-scan filter criteria
2. `UniverseFilters` applied in Phase 1 before OHLCV fetch (except `ohlcv_min_bars`)
3. `ScoringFilters` applied between Phase 2 and Phase 3 in the orchestrator
4. `OptionsFilters` applied in Phase 3 with earnings check before chain fetch
5. Market cap tier filtering uses cached `ticker_metadata` — no API call
6. New `min_score` filter drops tickers below threshold after Phase 2
7. New `min_direction_confidence` filter drops tickers below threshold after Phase 2
8. CLI `--min-score` and `--min-confidence` flags exposed
9. API `ScanRequest` accepts `min_score` and `min_direction_confidence`
10. Default `ScanFilterSpec()` produces identical behavior to current defaults
11. Remove unused `options_batch_size` from `ScanConfig`
12. Consolidate `dte_min`/`dte_max` — single source in `OptionsFilters`

### Non-Functional Requirements

1. Full S&P 500 scan completes in under 8 minutes
2. No regression in existing scan behavior when using default filter values
3. All filter models are `frozen=True` (immutable)
4. All numeric validators use `math.isfinite()` guard
5. Filter spec is serializable (can be persisted with scan results for reproducibility)

## API / CLI Surface

**CLI** (`options-arena scan`):
```
# Existing args (unchanged interface, new internal plumbing):
--preset sp500
--sector technology --sector healthcare
--industry-group "Software & Services"
--direction bullish
--top-n 30
--min-price 20 --max-price 500
--min-dte 30 --max-dte 90
--market-cap mega --market-cap large
--exclude-earnings 7
--min-iv-rank 30
--custom-tickers AAPL,MSFT,NVDA

# NEW args:
--min-score 40.0
--min-confidence 0.5
```

**API** (`POST /api/scan`):
Request body fields stay the same for backward compatibility. `ScanRequest` constructs `ScanFilterSpec` internally.

## Testing Strategy

**Unit tests (~40-50 new):**
- `test_filters.py` — model validation: all validators, edge cases (NaN, negative, boundary values), `min_dte > max_dte` rejection, delta range subset validation, custom_tickers normalization
- `test_phase_universe_filters.py` — market cap filter with cached metadata, price filter integration
- `test_phase_scoring_filters.py` — min_score cutoff, min_confidence cutoff, direction filter regression
- `test_phase_options_filters.py` — earnings pre-filter before chain fetch, IV rank filter, contract selection filter params
- `test_pipeline_filter_integration.py` — end-to-end: `ScanFilterSpec` flows through all 4 phases

**Edge cases:**
- Empty filter spec (all defaults) — identical to current behavior
- `min_score=100` — drops everything, scan completes with 0 results
- Market cap filter with empty metadata cache — skip filter, log warning
- `custom_tickers` + sector filter — custom_tickers bypasses sector (preserve existing behavior)
- DTE range excluding all expirations — 0 contracts, no crash

**Performance validation:**
- Benchmark scan with `min_score=30` vs without — measure Phase 3 ticker count reduction
- Benchmark market cap filter in Phase 1 vs Phase 3 — measure saved API calls

## Success Criteria

1. Single `ScanFilterSpec` model is the sole source of truth for all pre-scan filters
2. No filter-related fields remain on `ScanConfig` or `PricingConfig` (moved or deprecated)
3. Full S&P 500 scan completes in under 8 minutes
4. Market cap filtering happens before OHLCV fetch (Phase 1)
5. Earnings proximity filtering happens before chain fetch (Phase 3)
6. `min_score` cutoff demonstrably reduces Phase 3 ticker count
7. All existing tests pass with default filter values (no regression)
8. 40+ new unit tests covering filter models and phase integration

## Constraints & Assumptions

- **Python 3.13+** with Pydantic v2 conventions (frozen models, field_validator)
- Cached `ticker_metadata` table must be populated for market cap filtering in Phase 1; graceful degradation if empty
- `PricingConfig` still exists for non-filter pricing params (risk_free_rate_fallback, etc.)
- Post-scan API query filters (ScanFilterPanel, FilterPresets) are out of scope

## Out of Scope

- Post-scan result filtering (`GET /api/scan/{id}/scores` query params)
- Vue frontend result filter components (`ScanFilterPanel.vue`, `FilterPresets.vue`)
- `PreScanFilters.vue` UI changes (could be a follow-up epic)
- Predicate-based filter engine / dynamic filter evaluation
- Filter presets / saved filter configurations
- Custom ticker input UI in the frontend

## Dependencies

- **Internal**: `ticker_metadata` SQLite table (from metadata-index epic) must be populated for Phase 1 market cap filtering
- **Internal**: Pipeline phase decomposition (epic: pipeline-phase-extraction) — provides clean phase module boundaries
- **Internal**: Service layer unification (epic: service-layer-unification) — stable service interfaces
- **No external dependencies** — all filter logic is pure Python + Pydantic
