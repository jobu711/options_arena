---
name: post-v2-fixes
description: Fix critical export bug, eliminate raw dicts in API schema, and address consistency issues found in V2 agent outputs analysis
status: planned
created: 2026-03-04T17:10:51Z
---

# PRD: Post-V2 Agent Outputs — Bug Fixes & Type Safety

## Executive Summary

A comprehensive code analysis of commits `658ad3d..f3ce346` (the V2 Agent Outputs epic and
surrounding work) identified two critical issues, two medium-severity issues, and one
low-severity issue. The most urgent is a data loss bug where the export endpoint silently
drops all V2 agent outputs, producing incomplete markdown/PDF reports. The second is a
violation of the project's typed-model-everywhere rule in the API schema layer.

This PRD scopes the remediation work into a single focused epic that restores type safety
at the API boundary, fixes the export data loss, and addresses schema migration and
timezone consistency issues discovered during the analysis.

## Problem Statement

The V2 Agent Outputs feature (Epic 20) successfully wired six agent outputs through the
orchestrator, persistence, API, CLI, frontend, and export layers. However, the export
endpoint (`/api/debates/{id}/export`) reconstructs a `DebateResult` without populating any
V2 fields, silently producing V1-only exports for V2 debates. Additionally, the API schema
(`DebateResultDetail`) uses `dict[str, object] | None` for V2 response fields instead of
typed Pydantic models, violating the project's core architectural rule and losing type
safety at the API boundary.

These issues undermine the reliability of the export pipeline and the type guarantees that
the rest of the codebase depends on.

## User Stories

### US-1: Complete V2 Debate Export

**As** a user exporting a V2 debate to markdown or PDF,
**I want** the export to include all six agent outputs (trend, bear, flow, fundamental,
risk v2, contrarian),
**So that** the exported report accurately reflects the full debate that was displayed in
the CLI and web UI.

**Acceptance Criteria:**
- Exporting a V2 debate via `/api/debates/{id}/export?format=md` includes all V2 sections
- Exporting a V2 debate via CLI `--export md` includes all V2 sections
- Exporting a V1 debate still produces the correct V1 layout (no regression)
- Export includes `debate_protocol` field to distinguish V1 vs V2

### US-2: Type-Safe API Responses

**As** a frontend developer consuming the debate API,
**I want** V2 agent response fields to be typed Pydantic models (not raw dicts),
**So that** schema changes are caught at serialization time rather than silently passing
malformed data to the frontend.

**Acceptance Criteria:**
- `DebateResultDetail` uses `FlowThesis | None`, `FundamentalThesis | None`,
  `RiskAssessment | None`, `ContrarianThesis | None` instead of `dict[str, object] | None`
- Debate GET endpoint uses `model_validate_json()` instead of `json.loads()`
- Malformed V2 JSON in the database produces a clear 500 error, not silent garbage
- Existing frontend TypeScript interfaces remain compatible (no field renames)

### US-3: Consistent Timezone Handling

**As** a user running Options Arena on a non-US-timezone system,
**I want** outcome collection and expiry checks to use market-aware dates,
**So that** outcomes are not collected prematurely or contracts marked expired incorrectly.

**Acceptance Criteria:**
- `outcome_collector.py` uses `America/New_York` timezone for date comparisons
- Outcomes are never collected before US market close on the target date
- Contracts are not marked expired before their actual expiration in US Eastern time

## Requirements

### Functional Requirements

**FR-1: Fix export endpoint to populate V2 fields**
File: `src/options_arena/api/routes/export.py`

The `DebateResult` reconstruction at line ~136 must parse V2 JSON fields from the
`DebateRow` and pass them to the constructor:

```python
from options_arena.models import FlowThesis, FundamentalThesis, RiskAssessment, ContrarianThesis

flow_response = FlowThesis.model_validate_json(row.flow_json) if row.flow_json else None
fundamental_response = FundamentalThesis.model_validate_json(row.fundamental_json) if row.fundamental_json else None
risk_v2_response = RiskAssessment.model_validate_json(row.risk_v2_json) if row.risk_v2_json else None
contrarian_response = ContrarianThesis.model_validate_json(row.contrarian_json) if row.contrarian_json else None

result = DebateResult(
    ...,  # existing fields
    flow_response=flow_response,
    fundamental_response=fundamental_response,
    risk_v2_response=risk_v2_response,
    contrarian_response=contrarian_response,
    debate_protocol=row.debate_protocol,
)
```

**FR-2: Replace raw dicts with typed models in API schema**
File: `src/options_arena/api/schemas.py`

Change `DebateResultDetail` fields from:
```python
flow_response: dict[str, object] | None = None
fundamental_response: dict[str, object] | None = None
risk_v2_response: dict[str, object] | None = None
contrarian_response: dict[str, object] | None = None
```
To:
```python
flow_response: FlowThesis | None = None
fundamental_response: FundamentalThesis | None = None
risk_v2_response: RiskAssessment | None = None
contrarian_response: ContrarianThesis | None = None
```

**FR-3: Replace json.loads() with typed deserialization in debate route**
File: `src/options_arena/api/routes/debate.py`

At line ~585, replace:
```python
flow_response=json.loads(row.flow_json) if row.flow_json else None,
```
With:
```python
flow_response=FlowThesis.model_validate_json(row.flow_json) if row.flow_json else None,
```
Repeat for all four V2 fields. Remove `import json` if no longer used.

**FR-4: Add migration for contract_outcomes unique constraint**
File: `data/migrations/020_fix_outcomes_constraint.sql` (new)

Create a new migration that recreates the `contract_outcomes` table with the correct
`UNIQUE(recommended_contract_id, holding_days)` constraint for databases that already
ran the old migration 012:

```sql
-- Recreate contract_outcomes with correct unique constraint
CREATE TABLE IF NOT EXISTS contract_outcomes_new (
    -- same columns as current contract_outcomes
    UNIQUE(recommended_contract_id, holding_days)
);
INSERT OR IGNORE INTO contract_outcomes_new SELECT * FROM contract_outcomes;
DROP TABLE IF EXISTS contract_outcomes;
ALTER TABLE contract_outcomes_new RENAME TO contract_outcomes;
```

**FR-5: Use market-timezone-aware dates in outcome collector**
File: `src/options_arena/services/outcome_collector.py`

Replace `date.today()` at lines ~85 and ~298 with:
```python
from zoneinfo import ZoneInfo

_EASTERN = ZoneInfo("America/New_York")

def _market_today() -> date:
    return datetime.now(_EASTERN).date()
```

### Non-Functional Requirements

- **Backward compatibility**: V1 debates must continue to export and render correctly
- **Type safety**: All V2 fields at API boundary must be typed Pydantic models
- **Test coverage**: Each FR must have corresponding unit tests
- **No new dependencies**: Uses only `zoneinfo` (stdlib) and existing Pydantic models

## Success Criteria

| Metric | Target |
|--------|--------|
| V2 export includes all 6 agent sections | 100% of V2 debates |
| Raw dict fields in API schema | 0 (eliminated) |
| Export regression (V1 debates) | 0 test failures |
| Existing test suite | All 3,799+ tests pass |
| New tests added | >= 10 covering all 5 FRs |
| mypy --strict | Clean pass |
| ruff check | Clean pass |

## Constraints & Assumptions

**Constraints:**
- Migration 012 cannot be retroactively modified (IF NOT EXISTS prevents re-execution)
- SQLite does not support ALTER TABLE DROP CONSTRAINT — must use table recreation
- Export endpoint must remain backward compatible with V1 debate rows

**Assumptions:**
- All V2 JSON stored in `ai_theses` table is valid and matches current model schemas
- `zoneinfo` module is available (Python 3.9+, guaranteed by Python 3.13 requirement)
- No downstream consumers depend on the raw-dict shape of V2 API responses

## Out of Scope

- Refactoring V1 export logic or changing V1 debate format
- Adding new V2 agent types beyond the existing six
- Frontend changes (TypeScript interfaces already match the typed models)
- Performance optimization of export endpoint
- `relative_volume` scoring semantics change (intentional design decision, not a bug)

## Dependencies

**Internal:**
- `models/debate.py`: `FlowThesis`, `FundamentalThesis`, `RiskAssessment`, `ContrarianThesis`
- `models/scan.py`: `DebateResult`, `DebateRow`
- `data/repository.py`: `_row_to_debate()` (already returns V2 JSON strings)
- `reporting/debate_export.py`: V2 section renderers (already implemented)

**External:**
- None (all fixes use existing dependencies)

## Execution Order

| Step | FR | Files | Dependencies |
|------|----|-------|-------------|
| 1 | FR-2, FR-3 | `schemas.py`, `debate.py` | None (foundation) |
| 2 | FR-1 | `export.py` | FR-2 pattern to follow |
| 3 | FR-5 | `outcome_collector.py` | None (independent) |
| 4 | FR-4 | `migrations/020_*.sql` | None (independent) |
| 5 | Tests | `tests/` | All FRs complete |

Steps 1-2 are sequential (schema change informs export fix). Steps 3-4 can run in
parallel with steps 1-2.

## Files Modified

| File | Change |
|------|--------|
| `src/options_arena/api/schemas.py` | Replace `dict[str, object]` with typed models |
| `src/options_arena/api/routes/debate.py` | `model_validate_json()` instead of `json.loads()` |
| `src/options_arena/api/routes/export.py` | Populate V2 fields in DebateResult reconstruction |
| `src/options_arena/services/outcome_collector.py` | Market-timezone-aware `date.today()` replacement |
| `data/migrations/020_fix_outcomes_constraint.sql` | New migration for constraint fix |
| `tests/api/test_debate_routes.py` | Tests for typed V2 responses |
| `tests/api/test_export_routes.py` | Tests for V2 export completeness |
| `tests/services/test_outcome_collector.py` | Tests for timezone-aware date handling |
| `tests/data/test_migrations.py` | Test for migration 020 |
