# Research: post-v2-fixes

## PRD Summary

Fix five issues from the V2 Agent Outputs epic (Epic 20):
1. **FR-1**: Export endpoint silently drops all V2 agent outputs (data loss)
2. **FR-2**: API schema uses `dict[str, object]` instead of typed Pydantic models
3. **FR-3**: Debate route uses `json.loads()` instead of `model_validate_json()`
4. **FR-4**: Missing migration 020 for contract_outcomes unique constraint fix
5. **FR-5**: Outcome collector uses naive `date.today()` instead of market-timezone-aware dates

## Relevant Existing Modules

- `api/routes/export.py` — DebateResult reconstruction missing V2 field population (lines 136-146)
- `api/routes/debate.py` — V2 fields deserialized via `json.loads()` (lines 585-588) instead of typed models
- `api/schemas.py` — `DebateResultDetail` has `dict[str, object] | None` on 4 fields (lines 256-259)
- `services/outcome_collector.py` — Uses `date.today()` at lines ~85 and ~298 (naive timezone)
- `models/analysis.py` — Defines all 4 V2 models: `FlowThesis`, `FundamentalThesis`, `RiskAssessment`, `ContrarianThesis`
- `agents/_parsing.py` — `DebateResult` model already has V2 fields typed correctly
- `data/repository.py` — `DebateRow` dataclass correctly stores V2 JSON strings; `_row_to_debate_row()` works
- `reporting/debate_export.py` — V2 section renderers already implemented (lines 96-255, 322-335)

## Existing Patterns to Reuse

- **Model deserialization at route boundary**: `AgentResponse.model_validate_json(row.bull_json) if row.bull_json else None` (debate.py lines 533-534). Apply same pattern for V2 fields.
- **Export DebateResult construction**: export.py already builds DebateResult from DebateRow for V1 fields. Just add 4 more field assignments.
- **contextlib.suppress(Exception)**: Export route wraps deserialization in `contextlib.suppress()` for resilience. V2 fields should follow same pattern.
- **Timezone-aware dates**: `zoneinfo.ZoneInfo("America/New_York")` — stdlib, no new deps needed.
- **Migration pattern**: Sequential SQL files in `data/migrations/`. Latest is 019. New one is 020.

## Existing Code to Extend

| File | What Exists | What Needs Changing |
|------|-------------|---------------------|
| `api/schemas.py:256-259` | 4 `dict[str, object] \| None` fields | Change to `FlowThesis \| None`, etc. |
| `api/routes/debate.py:585-588` | `json.loads(row.flow_json)` | Change to `FlowThesis.model_validate_json(row.flow_json)` |
| `api/routes/export.py:136-146` | DebateResult() missing V2 fields | Add 4 field assignments + deserialization above |
| `services/outcome_collector.py:85,298` | `date.today()` | Replace with `_market_today()` using Eastern TZ |
| `data/migrations/` | 019 files exist | Add `020_fix_outcomes_constraint.sql` |

## Potential Conflicts

- **Frontend TypeScript interfaces**: `DebateResultDetail` field types change from `Record<string, unknown>` to structured objects. Frontend interfaces already match the typed model shapes (confirmed in PRD), so no conflict.
- **V1 backward compatibility**: All V2 fields are optional (`| None = None`). V1 debates will have `None` for all V2 fields, and export/renderers already check `is not None`. No conflict.
- **Migration 020 on fresh DBs**: `CREATE TABLE IF NOT EXISTS` + `INSERT OR IGNORE` pattern ensures idempotency. No conflict with existing migration 012.

## Open Questions

- **None** — PRD is highly prescriptive with exact file paths, line numbers, and code snippets.

## Recommended Architecture

This is a targeted bug-fix epic, not an architectural change. The fixes follow existing patterns:

1. **Schema fix (FR-2)**: Replace 4 field types in `DebateResultDetail` + add imports
2. **Route fix (FR-3)**: Replace 4 `json.loads()` calls with `model_validate_json()` + add imports, remove `import json` if unused
3. **Export fix (FR-1)**: Add 4 V2 deserialization lines + pass to DebateResult constructor
4. **Timezone fix (FR-5)**: Add `_market_today()` helper, replace 2 `date.today()` calls
5. **Migration (FR-4)**: New SQL file with table recreation pattern (SQLite lacks ALTER CONSTRAINT)

Execution order: FR-2 + FR-3 first (foundation), then FR-1 (follows pattern), then FR-4 + FR-5 in parallel, then tests.

## Test Strategy Preview

### Existing Test Patterns
- `tests/unit/api/test_debate_routes.py` — Mocks `repo.get_recent_debates()`, constructs `DebateRow` with `_make_debate_row()` fixture, asserts JSON response shape
- `tests/unit/api/test_repository_debates.py` — Tests round-trip DB persistence

### Missing Test Files (to create)
- `tests/api/test_export_routes.py` — Does not exist yet
- `tests/services/test_outcome_collector.py` — Does not exist yet

### New Tests Needed
| FR | Test File | What to Test |
|----|-----------|-------------|
| FR-1 | `test_export_routes.py` (new) | V2 debate export includes all 6 sections; V1 export unchanged |
| FR-2 | `test_debate_routes.py` (extend) | V2 fields are typed models, not dicts |
| FR-3 | `test_debate_routes.py` (extend) | Malformed V2 JSON returns clear error |
| FR-4 | `test_migrations.py` (new or extend) | Migration 020 recreates table correctly |
| FR-5 | `test_outcome_collector.py` (new) | `_market_today()` returns Eastern TZ date; `_is_expired()` uses market date |

### Mocking Strategy
- DB rows: Construct `DebateRow` with known V2 JSON strings
- Timezone: Use `freezegun` or `time_machine` to freeze datetime for timezone tests
- Repository: Mock `repo.get_debate_by_id()` to return V2-populated DebateRow

## Estimated Complexity

**Small (S)** — 5 targeted fixes across 5 files + ~10-15 new tests. All fixes follow existing patterns with exact code provided in PRD. No architectural decisions, no new dependencies, no API shape changes. Estimated 5-8 files modified/created total.
