---
name: pre-scan
status: backlog
created: 2026-03-06T14:19:52Z
progress: 0%
prd: .claude/prds/pre-scan.md
github: https://github.com/jobu711/options_arena/issues/280
---

# Epic: pre-scan

## Overview

Redesign the pre-scan filter panel by extracting filters from ScanPage.vue (398 lines) into a new `PreScanFilters.vue` component with 3 collapsible sections, adding 3 new universe presets (Nasdaq 100, Russell 2000, Most Active), 2 new range filters (price, DTE), estimated ticker counts per preset, and educational descriptions. All backend infrastructure exists — this is pattern-following across models, services, pipeline, API, and frontend.

## Architecture Decisions

- **PrimeVue Panel** for collapsible sections — project standard (used in SectorTree, ScanFilterPanel). Not Accordion.
- **Override wiring via `model_copy(update=dict)`** — extend existing pattern in `scan.py:123-144` for 4 new fields.
- **DTE forwarding**: `min_dte`/`max_dte` from `ScanRequest` override `PricingConfig.dte_min`/`dte_max` via `model_copy` on `AppSettings.pricing`. Same immutable copy pattern as scan overrides.
- **Russell 2000 = metadata `SMALL` tier proxy** — not official index. Label says "Small-cap equities." Include both SMALL and MICRO tiers for broader coverage.
- **Most Active = curated seed list** hardcoded in `universe.py` (~250 names). Same pattern as existing S&P 500 fallback list. No external data file.
- **Preset-info endpoint** at `GET /api/universe/preset-info` in `api/routes/universe.py` (universe-related).

## Technical Approach

### Backend (Waves 1–3)

**Wave 1 — Foundation (~95 LOC)**:
- `models/enums.py`: Add `NASDAQ100`, `RUSSELL2000`, `MOST_ACTIVE` to `ScanPreset` StrEnum.
- `models/config.py`: Add `max_price: float | None = None`, `min_dte: int | None = None`, `max_dte: int | None = None` to `ScanConfig` with validators (`isfinite`, range bounds) + cross-field `model_validator`.
- `api/schemas.py`: Add 4 optional fields to `ScanRequest` + new `PresetInfo` response model.
- `api/routes/scan.py`: 4 new override branches + DTE forwarding to `PricingConfig`.

**Wave 2 — Universe Service (~180 LOC)**:
- `services/universe.py`: 3 new fetch methods following cache-first, 24h TTL, never-raises pattern.
  - `fetch_nasdaq100_constituents()`: GitHub CSV → parse → CBOE cross-ref → curated fallback.
  - `fetch_russell2000_tickers()`: Metadata index query (`market_cap_tier in {SMALL, MICRO}`) → CBOE cross-ref.
  - `fetch_most_active()`: Curated seed list → CBOE cross-ref.
- `api/routes/universe.py`: `GET /api/universe/preset-info` returning `list[PresetInfo]` via `asyncio.gather`.

**Wave 3 — Pipeline + CLI (~45 LOC)**:
- `scan/pipeline.py`: 3 new preset dispatch branches in Phase 1 (~line 304). `max_price` filter in Phase 3 (~line 604).
- `cli/commands.py`: Update `--preset` help text to list all 6 presets.

### Frontend (Wave 4)

**Wave 4 — Frontend (~330 LOC new, ~270 LOC removed)**:
- `web/src/types/scan.ts`: Add `PresetInfo` interface + `PreScanFilterPayload` type.
- `web/src/stores/scan.ts`: Extend `StartScanOptions` with `min_price`, `max_price`, `min_dte`, `max_dte`.
- `web/src/components/scan/PreScanFilters.vue` (~300 lines): 3 collapsible Panel sections with active filter count badges, preset selector with ticker count badges, min/max price + DTE InputNumber controls, educational descriptions. Emits `@update:filters` with typed payload.
- `web/src/pages/ScanPage.vue`: Refactor from 398 → ~130 lines. Compose PreScanFilters + Run button + ProgressTracker + Past Scans table.

## Implementation Strategy

- **Wave 1 first** (foundation) — all subsequent waves depend on enums + config + schemas.
- **Waves 2, 3, 4 are independent** after Wave 1 — can be done in any order or in parallel.
- **Tests accompany each wave** — no wave is complete without passing tests.
- **E2E preservation**: Grep `data-testid` before and after ScanPage refactor to verify nothing lost.

## Task Breakdown

- [ ] Task 1: Backend foundation — Add 3 `ScanPreset` members, 3 `ScanConfig` fields with validators, 4 `ScanRequest` fields + `PresetInfo` model, scan route override wiring + DTE forwarding. Tests for enums, config validators, schema validation, route overrides.
- [ ] Task 2: Universe service — 3 new fetch methods (`fetch_nasdaq100_constituents`, `fetch_russell2000_tickers`, `fetch_most_active`) with caching + fallbacks. New `GET /api/universe/preset-info` endpoint. Tests for service methods + endpoint.
- [ ] Task 3: Pipeline + CLI — 3 new preset dispatch branches in Phase 1, `max_price` filter in Phase 3, CLI help text update. Tests for pipeline dispatch + price filtering.
- [ ] Task 4: Frontend — Add TS types, extend store, build `PreScanFilters.vue` component, refactor `ScanPage.vue` to <150 lines. Preserve all `data-testid` attributes.
- [ ] Task 5: E2E tests — ~4 new Playwright tests for PreScanFilters interaction (preset selection, price range, DTE range, collapsible sections).
- [ ] Task 6: Integration verification — Full test suite pass, lint, typecheck, manual smoke test of scan flow with new presets and filters.

## Dependencies

### Internal
- `ScanPreset` enum → config fields → ScanRequest schema → route wiring (sequential)
- Universe service methods → preset-info endpoint (sequential)
- Pipeline branches depend on enum members only
- Frontend depends on all backend being complete (API contract must be stable)

### External
- Nasdaq-100 CSV from GitHub/datahub (with curated fallback — no hard dependency)
- No new package dependencies

## Success Criteria (Technical)

- `ScanPage.vue` < 150 lines
- 6 preset options in UI and API
- 4 new filter controls (min/max price, min/max DTE) functional end-to-end
- `GET /api/universe/preset-info` returns counts for all 6 presets
- All existing 3,921+ Python tests pass
- All existing 38+ E2E tests pass unchanged
- New tests cover validators, service methods, pipeline branches, route wiring
- `ruff check`, `ruff format`, `mypy --strict` all pass

## Estimated Effort

| Wave | Scope | LOC (approx) |
|------|-------|---------------|
| 1 Backend Foundation | Enums, config, schemas, routes | ~125 (incl. tests) |
| 2 Universe Service | 3 fetch methods, preset-info endpoint | ~205 (incl. tests) |
| 3 Pipeline + CLI | 3 branches, max_price filter, CLI help | ~60 (incl. tests) |
| 4 Frontend | Types, store, PreScanFilters, ScanPage refactor | ~330 |
| 5 E2E Tests | ~4 Playwright tests | ~80 |
| 6 Integration | Verification pass | 0 LOC |
| **Total** | | **~800** |

## Tasks Created
- [ ] #285 - Backend foundation — enums, config, schemas, route wiring (parallel: false)
- [ ] #286 - Universe service — 3 fetch methods + preset-info endpoint (parallel: true)
- [ ] #287 - Pipeline dispatch branches + max_price filter + CLI update (parallel: true)
- [ ] #282 - Frontend — PreScanFilters component + ScanPage refactor (parallel: false)
- [ ] #283 - E2E tests for PreScanFilters interaction (parallel: false)
- [ ] #284 - Integration verification — full test suite + manual smoke test (parallel: false)

Total tasks: 6
Parallel tasks: 2 (#286 and #287 can run simultaneously after #285)
Sequential tasks: 4 (#285 → [#286, #287] → #282 → #283 → #284)
Estimated total effort: 19-28 hours

## Test Coverage Plan
Total test files planned: 7
Total test cases planned: ~46
