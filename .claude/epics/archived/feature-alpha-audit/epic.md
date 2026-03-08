---
name: feature-alpha-audit
status: completed
created: 2026-03-07T14:04:56Z
completed: 2026-03-07T16:05:00Z
progress: 100%
prd: .claude/prds/feature-alpha-audit.md
github: https://github.com/jobu711/options_arena/issues/329
---

# Epic: feature-alpha-audit

## Overview

Pure deletion epic — removes the watchlist feature (zero analytical value, 78+ tests,
~1,000 lines), drops dead DB artifacts (ghost table + dead column + orphaned watchlist
tables), and eliminates the PDF export path (weasyprint optional dependency). No new
code is written. Every change is a subtraction.

## Architecture Decisions

- **No DB migration for watchlist table creation rollback**: The `watchlists` and
  `watchlist_tickers` tables were created in `001_initial.sql`. Rather than editing
  that migration, we add a new migration `024` that drops them alongside the other
  dead artifacts. This preserves migration sequencing.
- **Leave `--export` flag accepting only `"md"`**: Rather than removing the flag
  entirely, keep it with a single valid value for backward compatibility. Users who
  had `--export md` in scripts are unaffected.
- **Atomic commits per phase**: Each task produces one commit. Any phase can be
  independently reverted with `git revert`.

## Technical Approach

### What's Being Removed

**Watchlist (FR-1):** Full-stack feature — Pydantic models, repository CRUD (10 methods),
API routes (6 endpoints), API schemas (4 classes), CLI subcommand (5 commands), Vue page,
Pinia store, TypeScript types, nav link, TickerDrawer integration, ScanResultsPage
integration, plus all unit tests (4 files) and E2E tests (3 files).

**Dead DB Artifacts (FR-2):** `intelligence_snapshots` ghost table (zero Python refs),
`ticker_scores.thematic_tags_json` dead column (zero production refs), `watchlists` table,
`watchlist_tickers` table.

**PDF Export (FR-3):** `_render_pdf()` function, weasyprint lazy import, PDF blocks in
CLI validation and API route, 1 test.

### No New Code

Zero new functions, models, or components. The only new file is migration `024`.

## Implementation Strategy

Sequential phases — each must pass verification before the next begins. Backend before
frontend (frontend imports backend types). DB cleanup after code removal (tables become
orphaned first, then dropped). PDF export is independent and runs last.

## Task Breakdown

- [ ] #330: Remove watchlist Python backend + unit tests
- [ ] #331: Remove watchlist frontend + E2E tests
- [ ] #332: Create DB cleanup migration
- [ ] #333: Remove PDF export path
- [ ] #334: Final verification and cleanup

## Dependencies

- **#330 before #331**: Frontend imports watchlist types from backend. Backend must be cleaned first so frontend removal doesn't hit stale imports during intermediate builds.
- **#330+#331 before #332**: Watchlist code must be removed before dropping its DB tables, so no code references orphaned tables.
- **#333 is independent**: Can run in parallel with #330-#332 but sequenced last for simplicity.
- **#334 after all others**: Final gate.

No external dependencies. No new packages. No API changes to external services.

## Success Criteria (Technical)

| Criteria | Verification |
|----------|-------------|
| Zero watchlist imports remaining | `grep -r "watchlist" src/ web/src/ --include="*.py" --include="*.ts" --include="*.vue"` returns 0 |
| Zero PDF/weasyprint refs in production code | `grep -r "weasyprint\|_render_pdf" src/` returns 0 |
| All Python tests pass | `uv run pytest tests/ -v` green |
| Type checking passes | `uv run mypy src/ --strict` green |
| Lint passes | `uv run ruff check .` green |
| Frontend builds | `cd web && npm run build` succeeds |
| Migration applies cleanly | SQLite migration 024 runs without error |
| Core flows work | Scan pipeline + debate produce results without errors |

## Tasks Created

- [ ] #330 - Remove watchlist Python backend + unit tests (parallel: false)
- [ ] #331 - Remove watchlist frontend + E2E tests (parallel: false, depends: #330)
- [ ] #332 - Create DB cleanup migration (parallel: true, depends: #330)
- [ ] #333 - Remove PDF export path (parallel: true, independent)
- [ ] #334 - Final verification and cleanup (parallel: false, depends: #330-#333)

Total tasks: 5
Parallel tasks: 2 (#332, #333)
Sequential tasks: 3 (#330, #331, #334)
Estimated total effort: 4-6.5 hours

## Test Coverage Plan

Total test files planned: 0 (deletion epic — no new tests)
Total test cases removed: ~90 (68 Python unit + ~20 E2E + 1 PDF test)
Test verification: full suite must pass after each task

## Estimated Effort

**Size: M (Medium)** — 5 tasks, ~2,350 lines removed, 0 lines added (excluding migration).
All changes are deletions with well-defined boundaries. Primary risk is a missed
cross-reference causing an import error, caught by verification gates between tasks.
