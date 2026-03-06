# Research: pre-scan

## PRD Summary

Redesign the pre-scan filter panel in ScanPage.vue (398 lines) into a new `PreScanFilters.vue` component with 3 collapsible PrimeVue Panel sections (Universe, Strategy, Price & Expiry). Add 3 new universe presets (Nasdaq 100, Russell 2000, Most Active), 2 new range filters (price, DTE), estimated ticker counts per preset, and educational descriptions on every control. Reduce ScanPage to <150 lines.

Backend: 3 new `ScanPreset` enum members, 2-3 new `ScanConfig` fields (`max_price`, `min_dte`, `max_dte`), 3 new `UniverseService` fetch methods, 1 new API endpoint (`GET /api/universe/preset-info`), 3 new pipeline dispatch branches, DTE override wiring.

## Relevant Existing Modules

- **`models/enums.py`** (line 104-114) — `ScanPreset(StrEnum)` has 3 members: FULL, SP500, ETFS. Add NASDAQ100, RUSSELL2000, MOST_ACTIVE.
- **`models/config.py`** (line 36-68) — `ScanConfig(BaseModel)` has `min_price: float = 10.0` but no `max_price`. `PricingConfig` (line 215-230) has `dte_min: int = 30`, `dte_max: int = 365`.
- **`api/schemas.py`** (line 36-49) — `ScanRequest` has 11 fields but no `min_price`, `max_price`, `min_dte`, `max_dte`. New `PresetInfo` response model needed.
- **`api/routes/scan.py`** (line 99-170) — Override wiring at lines 123-144 uses `model_copy(update=dict)` pattern. Add 4 new override branches.
- **`api/routes/universe.py`** (line 38-276) — 6 existing endpoints. Add `GET /api/universe/preset-info`.
- **`services/universe.py`** (line 153-400) — 3 fetch methods: `fetch_optionable_tickers()`, `fetch_sp500_constituents()`, `fetch_etf_tickers()`. All cached 24h. Add 3 new methods.
- **`scan/pipeline.py`** (line 207-439 Phase 1, line 589-613 Phase 3) — Preset dispatch at lines 304-323 uses if/elif. Phase 3 liquidity filter applies `min_price` at line 604.
- **`cli/commands.py`** — Scan command with `--preset` option. Update help text + list branches.
- **`web/src/pages/ScanPage.vue`** (398 lines) — Flat layout: launch panel + filter row + sector tree + theme chips + progress + past scans. Extract into PreScanFilters.vue.
- **`web/src/stores/scan.ts`** — `StartScanOptions` interface (lines 72-83) needs 4 new fields.
- **`web/src/types/scan.ts`** — Add `PresetInfo` interface and `PreScanFilterPayload` type.

## Existing Patterns to Reuse

### 1. Override Wiring Pattern (`api/routes/scan.py:123-144`)
Conditional dict building + `model_copy(update=dict)` for immutable config overrides:
```python
scan_overrides: dict[str, object] = {}
if body.min_price is not None:
    scan_overrides["min_price"] = body.min_price
# ...
scan_override = settings.scan.model_copy(update=scan_overrides)
effective_settings = settings.model_copy(update={"scan": scan_override})
```
Reuse this exact pattern for `max_price`, `min_dte`, `max_dte`.

### 2. Universe Service Caching Pattern (`services/universe.py`)
Two-tier cache (in-memory LRU + SQLite WAL), 24h TTL via `TTL_REFERENCE`, cache-key constants, never-raises contract (return empty list on failure). New fetch methods must follow this.

### 3. Deduplication Pattern (`models/config.py:70-83`)
`list(dict.fromkeys(result))` for enum list deduplication in field validators.

### 4. PrimeVue Panel Pattern (`SectorTree.vue`, `ScanFilterPanel.vue`)
```vue
<Panel :header="headerWithBadge" :toggleable="true" :collapsed="defaultCollapsed">
  <div class="filter-grid"><!-- controls --></div>
</Panel>
```
Active filter count in header: `"Label (3)"`. Responsive grid inside.

### 5. Pipeline Preset Dispatch (`scan/pipeline.py:304-323`)
if/elif chain checking `ScanPreset` enum value, calling corresponding `UniverseService` method, intersecting with optionable set.

### 6. Scan Route Background Task Pattern (`api/routes/scan.py:99-170`)
Counter-based IDs, `asyncio.create_task()`, lock acquisition, settings override before pipeline.

### 7. ScanRequest Validator Pattern (`api/schemas.py:50-160`)
Auto-deduplication, string-to-enum conversion, range validation with clear error messages.

## Existing Code to Extend

### Backend

| File | What Exists | What Changes |
|------|-------------|--------------|
| `models/enums.py:104-114` | 3 `ScanPreset` members | Add 3 new members |
| `models/config.py:36-68` | `ScanConfig` with `min_price` | Add `max_price: float | None`, `min_dte: int | None`, `max_dte: int | None` + cross-field validator |
| `api/schemas.py:36-49` | `ScanRequest` with 11 fields | Add `min_price`, `max_price`, `min_dte`, `max_dte` fields + new `PresetInfo` model |
| `api/routes/scan.py:123-144` | 8 override branches | Add 4 new branches (min_price, max_price) + DTE forwarding to PricingConfig |
| `api/routes/universe.py:38-70` | `UniverseStats` endpoint | Add `GET /api/universe/preset-info` returning `list[PresetInfo]` |
| `services/universe.py:153-400` | 3 fetch methods + caching | Add `fetch_nasdaq100_constituents()`, `fetch_russell2000_tickers()`, `fetch_most_active()` |
| `scan/pipeline.py:304-323` | 3 preset dispatch branches | Add 3 new branches for NASDAQ100, RUSSELL2000, MOST_ACTIVE |
| `scan/pipeline.py:589-613` | Phase 3 `min_price` filter | Add `max_price` filter alongside existing check |

### Frontend

| File | What Exists | What Changes |
|------|-------------|--------------|
| `web/src/pages/ScanPage.vue` | 398-line monolith | Extract filters into PreScanFilters.vue, reduce to ~130 lines |
| `web/src/stores/scan.ts` | `StartScanOptions` with 10 fields | Add `min_price`, `max_price`, `min_dte`, `max_dte` |
| `web/src/types/scan.ts` | Scan types | Add `PresetInfo`, `PreScanFilterPayload` interfaces |
| `web/src/components/scan/` | SectorTree, ThemeChips | Add `PreScanFilters.vue` (~300 lines) |

### New Files

| File | Purpose |
|------|---------|
| `web/src/components/scan/PreScanFilters.vue` | Extracted filter panel with 3 collapsible sections |

## Potential Conflicts

### 1. DTE Override vs PricingConfig
**Risk**: `PricingConfig.dte_min/dte_max` are used deep in scoring/contracts for contract selection. Overriding them per-scan requires careful forwarding.
**Mitigation**: Build `pricing_override` dict in scan route, apply via `model_copy(update={"pricing": pricing_override})` on `AppSettings`. Same pattern as `scan_overrides`.

### 2. `min_price` Field Naming
**Risk**: `ScanConfig.min_price` already exists (stock price floor, default $10). `ScanRequest` doesn't expose it yet. Adding `min_price` to `ScanRequest` maps directly to the existing config field.
**Mitigation**: PRD says use `min_price` in ScanRequest to map to existing `ScanConfig.min_price`. Add `max_price` as new field. Both are stock-price filters — naming is consistent.

### 3. E2E Test `data-testid` Preservation
**Risk**: Extracting filters into PreScanFilters.vue could break E2E tests if `data-testid` attributes move or disappear.
**Mitigation**: Preserve all existing `data-testid` values on extracted elements. Run `grep -r "data-testid" tests/e2e/` before/after to verify.

### 4. ScanPage.vue Reactivity After Extraction
**Risk**: Moving reactive state from ScanPage to PreScanFilters could break two-way binding.
**Mitigation**: Use `v-model` or `defineModel()` pattern. PreScanFilters emits `@update:filters` with complete payload. ScanPage holds source-of-truth state.

### 5. Nasdaq 100 CSV Source Reliability
**Risk**: External GitHub CSV may be unavailable or change format.
**Mitigation**: Curated fallback list of ~100 names hardcoded. Same pattern as existing SP500 fallback.

## Open Questions

1. **Russell 2000 source**: PRD says "metadata index `market_cap_tier == SMALL`" — should this include MICRO tier too? The actual Russell 2000 includes micro-caps. Need to confirm label wording.

2. **Most Active source**: PRD says "curated seed list ~250 names." Where should this list live? Hardcoded in `universe.py` or a JSON/CSV data file?

3. **DTE forwarding scope**: When user sets DTE range, does it override `PricingConfig.dte_min/dte_max` globally for the scan, or should it be a separate filter? PRD says "overrides PricingConfig" — confirm this means `model_copy` on `PricingConfig`.

4. **Preset-info endpoint location**: PRD says `GET /api/universe/preset-info`. Should it live in `api/routes/universe.py` (universe-related) or `api/routes/scan.py` (scan-configuration-related)?

## Recommended Architecture

### Backend Flow
```
ScanRequest (4 new fields)
  → scan route builds scan_overrides + pricing_overrides
  → model_copy on AppSettings (both scan + pricing configs)
  → Pipeline Phase 1: match on 6 ScanPreset values, dispatch to UniverseService
  → Pipeline Phase 3: apply max_price filter alongside existing min_price
  → Contract selection uses overridden PricingConfig.dte_min/dte_max
```

### Frontend Flow
```
ScanPage.vue (~130 lines)
  ├── PreScanFilters.vue (~300 lines, 3 Panel sections)
  │   ├── Panel "Universe": preset selector + SectorTree + estimated count badge
  │   ├── Panel "Strategy": market cap, direction, IV rank, themes, earnings
  │   └── Panel "Price & Expiry": min/max price, min/max DTE
  ├── Button "Run Scan"
  ├── ProgressTracker
  └── Past Scans DataTable
```

### New Universe Service Methods
```python
# All follow existing pattern: cache-first, 24h TTL, never-raises
fetch_nasdaq100_constituents() -> list[str]   # GitHub CSV + CBOE cross-ref + fallback
fetch_russell2000_tickers() -> list[str]      # Metadata query market_cap_tier=SMALL + CBOE cross-ref
fetch_most_active() -> list[str]              # Curated seed list + CBOE cross-ref
```

### New API Endpoint
```python
GET /api/universe/preset-info -> list[PresetInfo]
# PresetInfo: { preset: str, label: str, description: str, estimated_count: int }
# Uses asyncio.gather for parallel count fetches from cached data
```

## Test Strategy Preview

### Existing Test Patterns
- **Unit tests**: `tests/unit/` mirrors `src/options_arena/` structure. Each module has its own test directory.
- **Model tests**: `tests/unit/models/test_config.py` — validator edge cases, cross-field validation.
- **Service tests**: `tests/unit/services/test_universe.py` — mock httpx, test caching, test fallbacks.
- **API tests**: `tests/unit/api/` — TestClient-based, mock services via dependency override.
- **Pipeline tests**: `tests/unit/scan/test_pipeline.py` — mock services, verify phase outputs.
- **E2E tests**: `tests/e2e/` — Playwright, 38 tests, 4 parallel workers, isolated DBs.

### New Tests Needed
- **Enum tests**: 3 new `ScanPreset` values serialize/deserialize correctly.
- **Config tests**: `max_price`, `min_dte`, `max_dte` validators, cross-field `min <= max`.
- **Schema tests**: `ScanRequest` with new fields, `PresetInfo` serialization.
- **Route tests**: Override wiring for 4 new fields, DTE forwarding to PricingConfig.
- **Service tests**: 3 new fetch methods — cache hit/miss, fallback on failure, CBOE cross-ref.
- **Pipeline tests**: 3 new preset dispatch branches, `max_price` filter in Phase 3.
- **E2E tests**: ~4 new Playwright tests for PreScanFilters interaction.

### Mocking Strategy
- **Universe service**: Mock `fetch_*` methods to return curated ticker lists.
- **httpx**: Mock external CSV fetches (Nasdaq 100 GitHub source).
- **Repository**: Mock `get_all_ticker_metadata()` for Russell 2000 query.
- **Cache**: Use `ServiceCache` with in-memory backend for unit tests.

## Estimated Complexity

**L (Large)** — Justification:
- Touches 8+ backend files across 5 modules (models, services, scan, api, cli)
- 1 new frontend component (~300 lines) + ScanPage refactor
- 3 new universe service methods with external data sources + fallbacks
- 1 new API endpoint
- DTE override wiring crosses config boundary (ScanConfig → PricingConfig)
- ~70+ new tests across unit and E2E
- ~724 LOC total (320 backend + 330 frontend + 74 tests)
- 4 implementation waves with dependency chain

However, all patterns exist — no new architectural concepts. Execution is pattern-following, not invention.
