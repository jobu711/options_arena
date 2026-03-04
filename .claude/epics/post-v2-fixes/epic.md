---
name: post-v2-fixes
status: backlog
created: 2026-03-04T17:17:25Z
progress: 0%
prd: .claude/prds/post-v2-fixes.md
github: https://github.com/jobu711/options_arena/issues/257
---

# Epic: post-v2-fixes

## Overview

Targeted bug-fix epic addressing five issues found in the V2 Agent Outputs work (Epic 20).
The most critical is a data loss bug where export silently drops all V2 agent outputs.
Second is a typed-model violation (`dict[str, object]`) in the API schema. Also fixes
timezone-naive date comparisons in outcome collection and adds a corrective DB migration.

All fixes follow existing codebase patterns — no new dependencies, no architecture changes.

## Architecture Decisions

- **No new patterns**: Every fix reuses an existing pattern (e.g., `model_validate_json()` for
  JSON→model, `contextlib.suppress()` for resilient parsing, `ZoneInfo` for timezone).
- **No frontend changes**: TypeScript interfaces already match the typed model shapes.
- **Corrective migration**: Migration 020 uses SQLite table-recreation pattern (no ALTER CONSTRAINT
  support) with `IF NOT EXISTS` + `INSERT OR IGNORE` for idempotency.

## Technical Approach

### API Layer (FR-2, FR-3)
- `schemas.py`: Replace 4 `dict[str, object] | None` fields with typed models (`FlowThesis`,
  `FundamentalThesis`, `RiskAssessment`, `ContrarianThesis`)
- `routes/debate.py`: Replace 4 `json.loads()` calls with `Model.model_validate_json()`,
  add model imports, remove `import json` if unused

### Export Layer (FR-1)
- `routes/export.py`: Deserialize 4 V2 JSON fields from `DebateRow` using same
  `contextlib.suppress()` pattern as V1 fields, pass to `DebateResult` constructor

### Outcome Collector (FR-5)
- `services/outcome_collector.py`: Add `_market_today()` helper using
  `ZoneInfo("America/New_York")`, replace 2 `date.today()` calls

### Database Migration (FR-4)
- `data/migrations/020_fix_outcomes_constraint.sql`: Recreate `contract_outcomes` with correct
  `UNIQUE(recommended_contract_id, holding_days)` constraint

## Implementation Strategy

### Execution Order
1. **Wave 1** (sequential): FR-2 + FR-3 (schema + debate route) — foundation
2. **Wave 2** (depends on Wave 1 pattern): FR-1 (export endpoint)
3. **Wave 3** (independent, parallel-safe): FR-4 (migration) + FR-5 (timezone)
4. **Wave 4**: Tests for all FRs + full verification

### Risk Mitigation
- V1 backward compatibility: All V2 fields remain `| None = None`
- Resilient parsing: `contextlib.suppress(Exception)` in export (matches existing pattern)
- Migration idempotency: `IF NOT EXISTS` + `INSERT OR IGNORE`

## Task Breakdown Preview

- [ ] Task 1: Type-safe API schema + debate route deserialization (FR-2 + FR-3)
- [ ] Task 2: Export endpoint V2 field population (FR-1)
- [ ] Task 3: Market-timezone-aware dates in outcome collector (FR-5)
- [ ] Task 4: Migration 020 for contract_outcomes constraint (FR-4)
- [ ] Task 5: Tests for all FRs + lint/typecheck/test verification

## Dependencies

**Internal (all already exist):**
- `models/analysis.py`: `FlowThesis`, `FundamentalThesis`, `RiskAssessment`, `ContrarianThesis`
- `agents/_parsing.py`: `DebateResult` (already has V2 fields)
- `data/repository.py`: `DebateRow` (already has V2 JSON strings)
- `reporting/debate_export.py`: V2 section renderers (already implemented)

**External:** None

## Success Criteria (Technical)

| Gate | Target |
|------|--------|
| `ruff check . && ruff format --check .` | Clean |
| `mypy src/ --strict` | Clean |
| `pytest tests/ -v` | All 3,799+ existing tests pass |
| New tests added | >= 10 covering all 5 FRs |
| Raw `dict` fields in API schema | 0 |
| V2 export completeness | All 4 V2 sections present |

## Tasks Created
- [ ] #258 - Type-safe API schema and debate route deserialization (FR-2 + FR-3) (parallel: false)
- [ ] #259 - Fix export endpoint to populate V2 fields (FR-1) (parallel: false, depends: #258)
- [ ] #260 - Market-timezone-aware dates in outcome collector (FR-5) (parallel: true)
- [ ] #261 - Migration 020 for contract_outcomes unique constraint (FR-4) (parallel: true)
- [ ] #262 - Full verification pass — lint, typecheck, test suite (parallel: false, depends: #258-#261)

Total tasks: 5
Parallel tasks: 2 (#260, #261)
Sequential tasks: 3 (#258 → #259, then #262 after all)
Estimated total effort: 4-7 hours

## Test Coverage Plan
Total test files planned: 4 (test_debate_routes_v2.py, test_schemas.py, test_export_routes.py, test_outcome_collector.py, test_migration_020.py)
Total test cases planned: 14

## Estimated Effort

**Small (S)** — 5 source files modified, 1 new migration, ~10-15 new tests.
All changes follow existing patterns with prescriptive code in the PRD.
5 tasks, single-developer, single session.
