---
name: dead-code-cleanup-orphans
status: backlog
created: 2026-03-23T13:21:12Z
progress: 0%
prd: .claude/prds/dead-code-cleanup.md
parent_epic: dead-code-cleanup
depends_on: []
worktree: ../wt-orphans
branch: epic/dead-code-cleanup-orphans
github: https://github.com/jobu711/options_arena/issues/708
---

# Epic: dead-code-cleanup-orphans

## Overview

Wave 3: Remove orphaned infrastructure that was built but never connected to any
production path. Three large subsystems — IntelligenceService (~997 lines),
14 dead API endpoints (~330 lines), and the eval harness (~1,024 lines) — plus
a decision on neural pricing modules (734 lines).

## Scope Boundary

### In Scope
- FR-3.1: Remove `IntelligenceService` + models (~997 lines)
- FR-3.2: Remove 14 dead API endpoints (~330 lines)
- FR-3.3: Remove eval harness framework (~1,024 lines)
- FR-3.4: Decide on neural pricing modules (734 lines)

### Out of Scope (handled by sibling epics)
- Individual dead function deletion (Wave 1: quickwins)
- Rendering/helper refactoring (Wave 2: refactor)
- process_ticker_options, debate sunset (Wave 4: sunset)

## Technical Approach

### FR-3.1: IntelligenceService removal (~997 lines)

The `IntelligenceService` is instantiated in `api/app.py` when `settings.intelligence.enabled=True`
(the default), but `recommendation_orchestrator.py` calls `build_market_context()` without the
`intelligence=` kwarg — data NEVER reaches any analysis path.

Files to modify/delete:
- **Delete**: `services/intelligence.py` (583 lines)
- **Delete**: `models/intelligence.py` (414 lines)
- **Edit**: `models/config.py` — remove `IntelligenceConfig` class
- **Edit**: `models/config.py` — remove `intelligence` field from `AppSettings`
- **Edit**: `models/__init__.py` — remove intelligence model re-exports
- **Edit**: `api/app.py` — remove `IntelligenceService` from lifespan
- **Edit**: `api/deps.py` — remove intelligence dependency provider (if exists)
- **Edit**: `agents/_context.py` or `_parsing.py` — remove `intelligence=` kwarg from `build_market_context()` signature
- **Delete**: `tests/unit/services/test_intelligence*.py`
- **Delete**: `tests/unit/models/test_intelligence*.py`

### FR-3.2: Remove 14 dead API endpoints (~330 lines)

Zero frontend callers confirmed. CLI commands providing the same functionality are NOT affected.

From `api/routes/analytics.py`:
- `GET /api/analytics/indicator-attribution/{indicator}` (~15 lines)
- `GET /api/analytics/risk-metrics` (~12 lines)
- `GET /api/analytics/correlation` (~50 lines)
- `GET /api/analytics/recommendation-costs` (~20 lines)
- `GET /api/analytics/scan/{scan_id}/contracts` (~15 lines)

From `api/routes/learning.py` (entire file removable):
- All 7 `GET/POST /api/learning/*` endpoints (~120 lines)

From `api/routes/eval.py` (entire file removable):
- All 4 `GET/POST /api/eval/*` endpoints (~60 lines)

From `api/routes/universe.py`:
- `POST /api/universe/refresh` (~15 lines)
- `POST /api/universe/index` (~15 lines)
- `GET /api/universe/metadata/stats` (~10 lines)

Also remove:
- Route registrations from `api/app.py` (for deleted route files)
- Response schemas from `api/schemas.py` that are only used by deleted endpoints

### FR-3.3: Remove eval harness framework (~1,024 lines)

Zero eval definitions exist. The framework cannot produce value.

Files to delete:
- `evals/runner.py` (400 lines)
- `evals/graders.py` (465 lines)
- `evals/__init__.py`
- `models/eval.py` (159 lines)
- `data/_eval.py` — remove `EvalMixin` (note: quickwins deletes singular `get_eval_definition` — this epic deletes the entire mixin)

Files to edit:
- `models/config.py` — remove `EvalConfig` class + field from `AppSettings`
- `models/__init__.py` — remove eval model re-exports
- `data/repository.py` — remove `EvalMixin` from `Repository` class inheritance
- `data/__init__.py` — remove eval re-exports
- `cli/` — remove `eval` subcommand registration

Migration 039 (`eval_runs` table): Leave the migration file in place (SQLite migrations
are append-only), but the table becomes unused. A future migration can drop it.

Test files to delete:
- `tests/unit/evals/test_eval_runner.py`
- `tests/unit/evals/test_eval_persistence.py`
- `tests/unit/evals/test_eval_graders.py`
- `tests/unit/models/test_eval.py`

### FR-3.4: Neural pricing decision

`trajectory.py` (408 lines) + `neural_surface.py` (326 lines) = 734 lines behind
optional `[neural]` extra (PyTorch + Lightning) that isn't shipped.

Options:
- **(a) Keep with documentation**: Add module docstrings noting optional/experimental status
- **(b) Remove**: Delete files, remove `[neural]` from `pyproject.toml` optional-dependencies

Recommendation: **(a) Keep** — the code is well-tested, behind guarded imports, and
doesn't affect users who don't install `[neural]`. Removal gains no runtime benefit.
Add `# EXPERIMENTAL: requires [neural] extra` header comment to each file.

## Tasks Created

- [ ] #713 - Delete IntelligenceService + models (parallel: true)
- [ ] #718 - Remove IntelligenceConfig from settings + lifespan wiring (parallel: false, depends: #713)
- [ ] #726 - Remove 5 dead analytics API endpoints (parallel: true)
- [ ] #735 - Remove learning API routes — entire file (parallel: true)
- [ ] #739 - Remove eval API routes — entire file (parallel: true)
- [ ] #714 - Remove 3 dead universe API endpoints (parallel: true)
- [ ] #720 - Delete eval harness framework — runner, graders, models (parallel: true)
- [ ] #733 - Remove EvalMixin from Repository + EvalConfig from settings + CLI eval subcommand (parallel: false, depends: #720)
- [ ] #742 - Document neural pricing modules as experimental (parallel: true)
- [ ] #743 - Verification — lint + typecheck + tests + docs regen (parallel: false, depends: all)

Total tasks: 10
Parallel tasks: 6 (#713, #726, #735, #739, #714, #720, #742)
Sequential tasks: 4 (#718→#713, #733→#720, #743→all)
Estimated total effort: 2.5 hours

## Test Coverage Plan
Total test files planned: 0 (deletion epic — existing tests removed, no new tests)
Total test cases planned: 0 (verification via existing suite minus deleted tests)

## Shared File Conflicts (with sibling epics)

| File | This epic | Conflict with |
|------|-----------|---------------|
| `models/config.py` | del IntelligenceConfig, EvalConfig | quickwins (del num_ctx), refactor (FiniteFieldsMixin) |
| `models/__init__.py` | del eval/intelligence re-exports | quickwins (del dead model re-exports) |
| `data/_eval.py` | del entire mixin | quickwins (del singular method) |
| `data/repository.py` | remove EvalMixin | — |
| `api/app.py` | remove intelligence lifespan | — |

Resolution: rebase onto master after quickwins + refactor merge. Non-overlapping changes.

## Dependencies

- None (executes in parallel, merges third)

## Success Criteria

- `IntelligenceService` + models fully removed (~997 lines)
- 14 dead API endpoints removed (~330 lines)
- Eval harness fully removed (~1,024 lines)
- Neural pricing decision documented
- CLI commands for learning/eval/universe unaffected
- All tests pass

## Estimated Effort

- 10 tasks
- ~2-3 hours wall-clock
- Merges third (rebase after quickwins + refactor)
