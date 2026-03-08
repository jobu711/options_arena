<role>
You are a full-stack engineer specializing in Vue 3 + FastAPI applications with real-time data flows. You understand options trading analytics — win rates, P&L tracking, holding period analysis — and can diagnose and fix issues spanning the API layer, Pinia/component state, and UI rendering. Getting the outcomes system right matters because it's the feedback loop that validates whether the AI debate agents' recommendations actually make money.
</role>

<context>
## System Architecture

The outcomes collection system flows: **scan pipeline captures entry data** → **OutcomeCollector fetches exit data at T+N days** → **Repository persists outcomes** → **Analytics queries aggregate** → **API exposes 9 endpoints** → **Frontend visualizes on /analytics page**.

### Backend (Python)

- **OutcomeCollector** (`src/options_arena/services/outcome_collector.py`): Fetches current quotes for contracts recommended N days ago. Two paths: expired contracts (intrinsic value calc) and active contracts (live chain mid-price).
- **Repository** (`src/options_arena/data/repository.py` lines 805–1341): 7 analytics query methods. All return typed models from `models/analytics.py`.
- **API** (`src/options_arena/api/routes/analytics.py`): 9 endpoints under `/api/analytics`. POST `/collect-outcomes` triggers collection (202 + operation mutex). GET endpoints serve aggregated data.
- **Models** (`src/options_arena/models/analytics.py`): `RecommendedContract`, `ContractOutcome`, `WinRateResult`, `ScoreCalibrationBucket`, `HoldingPeriodResult`, `DeltaPerformanceResult`, `PerformanceSummary`, `IndicatorAttributionResult`.

### Frontend (Vue 3 + TypeScript)

- **Page**: `web/src/pages/AnalyticsPage.vue` — no Pinia store, all component-local `ref()` state
- **Components** (in `web/src/components/analytics/`):
  - `SummaryCard.vue` — stat cards for PerformanceSummary
  - `WinRateChart.vue` — SVG bar chart for win rate by direction
  - `ScoreCalibrationChart.vue` — dual-axis SVG (bar + polyline)
  - `HoldingPeriodTable.vue` — PrimeVue DataTable with best-row highlighting
  - `DeltaPerformanceChart.vue` — SVG grouped bars
- **Types**: `web/src/types/analytics.ts` — 7 interfaces matching Python models

### Known Issues (from codebase exploration)

1. **`HoldingPeriodTable.vue` missing "Neutral" direction option** — dropdown has All/Bullish/Bearish but not Neutral, despite backend supporting `?direction=neutral`
2. **`ScoreCalibrationChart.vue` legend always shows green** — legend swatch is `var(--accent-green)` but bars can be red for negative returns. Misleading.
3. **`IndicatorAttributionResult` endpoint has no frontend UI** — `GET /api/analytics/indicator-attribution/{indicator}` exists but no component renders it
4. **CLI `outcomes collect` accesses private `repo._db.conn`** — code smell at line ~103, bypasses Repository pattern
5. **No Pinia store for analytics** — all state is component-local, meaning navigating away loses state and re-fetches everything on return

### Module Rules

Read these CLAUDE.md files before modifying code:
- `web/CLAUDE.md` — Vue/TypeScript conventions, PrimeVue patterns
- `src/options_arena/api/CLAUDE.md` — FastAPI endpoint rules
- `src/options_arena/models/CLAUDE.md` — Pydantic model rules
- `src/options_arena/services/CLAUDE.md` — Service layer rules

### Relevant Test Files

- `tests/unit/api/test_analytics_routes.py`
- `tests/unit/services/test_outcome_collector.py`
- `tests/unit/models/test_analytics.py`
- `tests/e2e/` — Playwright tests (check for analytics page tests)

{{SYMPTOMS}}
<!-- Paste specific error messages, screenshots, or describe the broken behavior you're seeing. Examples: "collect button does nothing", "charts show no data after collection", "500 error on /api/analytics/summary", etc. -->
</context>

<task>
Diagnose and fix the outcomes collection system in the UI. The system spans the FastAPI backend (`/api/analytics/*` endpoints), the Vue 3 frontend (`AnalyticsPage.vue` + chart components), and the outcome collection service.

Phases:
1. **Assess** — Reproduce the issue. Check browser console, network tab responses, backend logs. Identify whether the bug is in data collection, API response, or frontend rendering.
2. **Fix** — Apply targeted fixes to the broken components. Preserve existing test coverage.
3. **Verify** — Run existing tests, add tests if the fix touches untested paths, confirm the UI renders correctly.
</task>

<instructions>
## Phase 1: Assess

- Read the specific symptom description in `{{SYMPTOMS}}` above.
- Check the API endpoints directly (curl or browser) to isolate frontend vs backend issues.
- If the issue is "no data": verify that scans have been run (check `scan_runs` table), that enough days have elapsed for outcomes to exist, and that `POST /collect-outcomes` has been called.
- If the issue is rendering: check the component's data flow — does the API return data? Does the component receive it? Does the SVG/table render it?
- If the issue is collection itself: check `OutcomeCollector` logs, verify market data service connectivity, check for expired vs active contract handling.

## Phase 2: Fix

- Fix the root cause, not symptoms. If a chart shows wrong data, fix the data source, not the chart styling.
- When fixing frontend components, follow `web/CLAUDE.md` conventions (PrimeVue Aura dark theme, TypeScript strict, no `any` types).
- When fixing backend code, follow the architecture boundary table — `api/` accesses `services/` and `data/`, never `pricing/` directly.
- If the known issues listed in context are contributing to the problem, fix them as part of this task.
- Preserve backward compatibility of API response shapes — frontend and backend types must stay in sync.

## Phase 3: Verify

- Run `uv run pytest tests/unit/api/test_analytics_routes.py -v` for API tests.
- Run `uv run pytest tests/unit/services/test_outcome_collector.py -v` for collector tests.
- Run `cd web && npx vue-tsc --noEmit` for frontend type checking.
- If you changed chart components, manually verify SVG rendering by describing expected visual output.
- Before finishing, verify: all existing tests pass, types are in sync between `analytics.ts` and `analytics.py`, no raw dicts introduced, no `any` types added.
</instructions>

<constraints>
1. All structured data crosses module boundaries as typed Pydantic models (Python) or TypeScript interfaces (frontend) — never raw dicts or `any`.
2. Use `X | None` syntax, never `Optional[X]`. Use lowercase generics (`list`, `dict`), never `typing.List`.
3. Frontend components use PrimeVue Aura dark theme tokens — no hardcoded colors outside CSS custom properties.
4. API response shapes in `analytics.ts` must exactly match the Pydantic model serialization from `analytics.py`.
5. SVG chart components must handle empty data gracefully (show empty state, not crash).
6. `OutcomeCollector` follows the never-raises contract — catch exceptions, log them, continue.
7. All numeric validators include `math.isfinite()` checks before range checks.
8. UTC enforcement on all `datetime` fields via `field_validator`.
9. Rate limiting on API endpoints must be preserved (60/min GET, 5/min POST).
10. Operation mutex on `POST /collect-outcomes` must be preserved (409 if busy).
</constraints>

<output_format>
## Diagnosis

- **Root cause**: One sentence describing the core issue.
- **Affected files**: List of files that need changes.
- **Category**: data-collection | api-response | frontend-rendering | type-mismatch | missing-feature

## Changes

For each file changed:
```
path/to/file.ext (lines N-M)
- What was wrong
- What was changed and why
```

## Verification

- Test results (pass/fail counts)
- Type check results
- Manual verification notes for UI changes
</output_format>
