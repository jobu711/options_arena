# Research: feature-alpha-audit

## PRD Summary

Comprehensive audit of all 24 features in Options Arena, scoring each on a 4-dimension alpha
framework (user value, analytical quality, maintenance cost, coupling risk). The audit identifies:
- **2 removals**: watchlist feature (78+ tests, ~1,000 lines) + dead DB artifacts
- **4 simplifications**: debate export (PDF removal), OpenBB test reduction, intelligence investigation, metadata index
- **16 keeps**: core infrastructure and analytical features

This epic covers FR-1 (watchlist removal), FR-2 (dead DB artifacts + watchlist table drops),
and FR-3 (PDF export removal). FR-4 through FR-6 are deferred to future epics.

## Relevant Existing Modules

- `models/watchlist.py` — 4 Pydantic models (Watchlist, WatchlistTicker, WatchlistDetail, WatchlistTickerDetail), 115 lines
- `cli/watchlist.py` — 5 Typer subcommands (list, create, delete, add, remove), 194 lines
- `api/routes/watchlist.py` — 6 HTTP endpoints (CRUD), 167 lines
- `api/schemas.py` — 4 watchlist request/response schemas (~50 lines)
- `data/repository.py` — 10 watchlist methods (lines 561-662+)
- `models/__init__.py` — 4 watchlist re-exports (lines 93-98, 200-204)
- `cli/__init__.py` — watchlist import registration (line 11)
- `api/app.py` — watchlist router include (lines 171, 181)
- `reporting/debate_export.py` — PDF export path (lines 422-474)
- `data/migrations/010_intelligence_tables.sql` — ghost `intelligence_snapshots` table
- `data/migrations/016_add_industry_group.sql` — dead `thematic_tags_json` column

### Frontend Files

- `web/src/pages/WatchlistPage.vue` — full watchlist management page
- `web/src/stores/watchlist.ts` — Pinia store (129 lines)
- `web/src/types/watchlist.ts` — TypeScript interfaces (26 lines)
- `web/src/router/index.ts` — `/watchlist` route (lines 25-29)
- `web/src/App.vue` — nav link (line 31)
- `web/src/components/TickerDrawer.vue` — "Add to Watchlist" button (lines 17, 41-80)
- `web/src/pages/ScanResultsPage.vue` — watchlist store integration

### E2E Test Files

- `web/e2e/suites/watchlist/watchlist.spec.ts` — full E2E suite (193 lines)
- `web/e2e/fixtures/pages/watchlist.page.ts` — page object (60 lines)
- `web/e2e/fixtures/builders/watchlist.builders.ts` — test data builders (46 lines)

## Existing Patterns to Reuse

- **Module removal pattern**: Delete files, remove re-exports from `__init__.py`, remove router registrations from `app.py`. Well-established from past refactors.
- **Migration pattern**: Sequential `NNN_description.sql` files in `data/migrations/`. Latest is `023_drop_themes.sql`. Next: `024`.
- **SQLite ALTER TABLE DROP COLUMN**: Supported on Python 3.13 (ships SQLite 3.45.3, needs 3.35+).
- **Frontend route removal**: Delete page component, remove route from `router/index.ts`, remove nav link from `App.vue`.
- **Store cleanup**: Delete Pinia store file, remove imports from consuming components.

## Existing Code to Extend

No new code needed — this epic is purely deletion and cleanup.

## Files to Delete (FR-1: Watchlist)

### Python Backend (6 files, ~740 lines)
1. `src/options_arena/models/watchlist.py` (115 lines)
2. `src/options_arena/cli/watchlist.py` (194 lines)
3. `src/options_arena/api/routes/watchlist.py` (167 lines)

### Frontend (3 files, ~255 lines)
4. `web/src/pages/WatchlistPage.vue` (~100 lines)
5. `web/src/stores/watchlist.ts` (129 lines)
6. `web/src/types/watchlist.ts` (26 lines)

### Tests (4 unit + 3 E2E = 7 files, ~1,250 lines)
7. `tests/unit/models/test_watchlist.py` (193 lines)
8. `tests/unit/cli/test_watchlist_cli.py` (101 lines)
9. `tests/unit/api/test_watchlist_routes.py` (279 lines)
10. `tests/unit/data/test_repository_watchlist.py` (378 lines)
11. `web/e2e/suites/watchlist/watchlist.spec.ts` (193 lines)
12. `web/e2e/fixtures/pages/watchlist.page.ts` (60 lines)
13. `web/e2e/fixtures/builders/watchlist.builders.ts` (46 lines)

### Total: 13 files deleted, ~2,245 lines removed

## Files to Modify (FR-1: Watchlist)

| File | Change | Lines |
|------|--------|-------|
| `src/options_arena/models/__init__.py` | Remove 4 watchlist imports (lines 93-98) + `__all__` entries (lines 200-204) | ~10 |
| `src/options_arena/data/repository.py` | Remove 10 watchlist methods (lines 561-662+) | ~100 |
| `src/options_arena/api/app.py` | Remove watchlist router import + `include_router()` (lines 171, 181) | ~2 |
| `src/options_arena/api/schemas.py` | Remove 4 watchlist schema classes (lines 375-425) | ~50 |
| `src/options_arena/cli/__init__.py` | Remove watchlist import (line 11) | ~1 |
| `web/src/router/index.ts` | Remove `/watchlist` route (lines 25-29) | ~5 |
| `web/src/App.vue` | Remove nav link (line 31) | ~1 |
| `web/src/components/TickerDrawer.vue` | Remove watchlist store import, dropdown, button (lines 17, 41-80) | ~40 |
| `web/src/pages/ScanResultsPage.vue` | Remove watchlist store import and quick-add logic | ~10 |
| `web/src/types/index.ts` | Remove watchlist type re-exports | ~1 |

### Total: 10 files modified, ~220 lines changed

## Files to Create (FR-2: Dead DB Artifacts + Watchlist Tables)

| File | Content |
|------|---------|
| `data/migrations/024_drop_dead_db_artifacts.sql` | `DROP TABLE IF EXISTS intelligence_snapshots;` + `ALTER TABLE ticker_scores DROP COLUMN thematic_tags_json;` + `DROP TABLE IF EXISTS watchlists;` + `DROP TABLE IF EXISTS watchlist_tickers;` |

### Files to Modify (FR-2)

| File | Change |
|------|--------|
| `tests/unit/data/test_migration.py` | Remove `thematic_tags_json` from expected schema columns (line ~74); remove watchlist tables from expected tables |

## Files to Modify (FR-3: PDF Export Removal)

| File | Change | Lines Removed |
|------|--------|---------------|
| `src/options_arena/reporting/debate_export.py` | Remove `_render_pdf()` function, simplify `export_debate_to_file()` to md-only | ~50 |
| `src/options_arena/cli/commands.py` | Change `--export` validation from `("md", "pdf")` to `("md",)`, remove weasyprint error | ~5 |
| `src/options_arena/api/routes/export.py` | Remove PDF rendering block (lines 196-213), update validation and docstrings | ~20 |
| `tests/unit/reporting/test_debate_export.py` | Remove `test_export_pdf_raises_import_error_without_weasyprint` test + docstring ref | ~11 |

## Potential Conflicts

- **TickerDrawer shared component**: Removing watchlist button from TickerDrawer affects all callers (ScanResultsPage, etc.). Low risk — button removal is a simple UI subtraction.
- **E2E test fixtures**: Watchlist builders/page objects may be imported by shared E2E helpers. Need to verify no shared fixtures reference them.
- **PDF export CLI validation**: `--export` flag currently accepts `"md"` or `"pdf"`. After removal, only `"md"` is valid. Users passing `--export pdf` will get a clear error.

## Open Questions

1. **DashboardPage watchlist references**: Agent found `ScanResultsPage` has watchlist integration. Need to verify DashboardPage is clean (likely is).

## Recommended Architecture

### Implementation Phases

**Phase 1: Watchlist Backend Removal**
- Delete Python files (models, CLI, API routes, schemas)
- Remove re-exports, router registrations, repository methods
- Delete all Python unit tests
- Run: `uv run pytest tests/ -v && uv run mypy src/ --strict && uv run ruff check .`

**Phase 2: Watchlist Frontend Removal**
- Delete Vue page, Pinia store, TypeScript types
- Remove route, nav link, TickerDrawer button, ScanResultsPage integration
- Delete E2E tests and fixtures
- Run: `cd web && npm run build && npx playwright test`

**Phase 3: Dead DB Artifacts + Watchlist Table Drops**
- Create migration `024_drop_dead_db_artifacts.sql` (intelligence_snapshots, thematic_tags_json, watchlists, watchlist_tickers)
- Update test schema expectations
- Run: `uv run pytest tests/unit/data/ -v`

**Phase 4: PDF Export Removal**
- Remove `_render_pdf()` from `debate_export.py`
- Simplify `export_debate_to_file()` to md-only
- Update CLI `--export` validation (remove "pdf" option)
- Remove API PDF rendering block from `export.py`
- Remove PDF test
- Run: `uv run pytest tests/unit/reporting/ tests/unit/cli/ tests/unit/api/ -v`

### Rollback Strategy

Each phase is a single atomic commit. `git revert <commit>` restores the feature.

## Test Strategy Preview

- **Existing test patterns**: pytest with fixtures, mock-based service isolation, `@pytest.mark.asyncio` for async tests
- **Verification after removal**: Full test suite (`uv run pytest tests/ -v`) must pass with ~90 fewer tests
- **Frontend verification**: `npm run build` must succeed, Playwright E2E must pass with watchlist suite removed
- **No new tests needed** — this is purely removal

## Estimated Complexity

**M (Medium)** — Justified:
- High file count (13 deletions + 10 modifications) but all changes are deletions/removals
- Well-isolated feature with clear module boundaries
- No refactoring of remaining code needed
- No new functionality to design or test
- Cross-cutting frontend changes (TickerDrawer, ScanResultsPage) require care but are straightforward
- Database migration is trivial (2 SQL statements)
- Main risk: missing a cross-reference that causes import error at runtime
