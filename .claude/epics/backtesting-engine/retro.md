---
generated: 2026-03-10T02:00:00Z
epic: backtesting-engine
---

# Retrospective: backtesting-engine

## Effort Analysis

| Metric | Planned | Actual |
|--------|---------|--------|
| Total hours | 84h | ~0.5h |
| Tasks | 7 | 7 |
| Waves | 5 | 5 |
| Ratio | — | 0.006x |

### Per-Task Breakdown

| Task | Issue | Planned | Commit Time | Notes |
|------|-------|---------|-------------|-------|
| #430 Models + migration | S (4h) | 20:53 | Foundation models, no blockers |
| #432 Auto-scheduler | M (8h) | 20:50 | Independent, ran in parallel with #430 |
| #431 AnalyticsMixin queries | L (20h) | 21:02 | 7 queries, ~9 min after models |
| #433 CLI subcommands | S (4h) | 21:06 | 2 subcommands, ran in parallel with #434 |
| #434 API endpoints | M (8h) | 21:06 | 7 endpoints, thin REST layer |
| #435 Vue dashboard | XL (32h) | 21:14 | 5 tabs, 8 chart components, store |
| #436 E2E tests | S (8h) | 21:20 | 21 Playwright tests |

All 7 commits within a 30-minute window (20:50 - 21:20).

## Scope Analysis

| Metric | Planned | Delivered |
|--------|---------|-----------|
| Pydantic models | 7 | 7 |
| DB queries | 7 | 7 |
| API endpoints | 7 | 7 |
| CLI subcommands | 2 | 2 |
| Chart components | 6 | 8 |
| E2E tests | ~11 | 21 |
| Unit tests | ~102 | 129 |
| Total lines added | — | 5,736 |

Scope delivered >= scope planned. Extra: 2 bonus chart components, ~20 extra unit tests, ~10 extra E2E tests.

## Quality Assessment

| Indicator | Value |
|-----------|-------|
| Post-merge fixes | 0 |
| Ruff violations | 0 |
| Mypy errors | 0 |
| Test failures | 0 |
| NaN/Inf validators | All float fields covered |
| Frozen models | All 7 immutable |

## Learnings

1. **Wave execution worked well** — Task 1+3 parallel, Task 4+5 parallel, reducing critical path.
2. **Thin REST layer pattern** — API endpoints are trivial when repo methods return typed models. M estimate was generous.
3. **XL frontend estimate was correct in scope** but Claude's execution speed makes the time estimate irrelevant for proxy hours.
4. **E2E test location** — Tests ended up in `web/e2e/suites/analytics/` not `tests/e2e/`. This is the correct location per project conventions but differed from the task spec.
5. **Vue page naming** — `AnalyticsPage.vue` not `AnalyticsView.vue` — followed actual project convention over spec.

## Estimation Bias

Planned: 84h, Actual: ~0.5h, Ratio: 0.006x

This continues the pattern of significant overestimation for Claude-executed work. The estimates were reasonable for human developer effort but don't apply to AI-assisted development.
